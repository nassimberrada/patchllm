import os
from patchllm.scopes.builder import build_context
from patchllm.scopes.structure import _extract_symbols_by_regex
from patchllm.scopes.constants import LANGUAGE_PATTERNS

def test_extract_python_symbols():
    content = """
import os
class MyClass(Parent):
    def method_one(self, arg1): pass
async def top_level_async_func(): pass
    """
    patterns = LANGUAGE_PATTERNS['python']['patterns']
    symbols = _extract_symbols_by_regex(content, patterns)
    assert "import os" in symbols["imports"]
    assert "class MyClass(Parent):" in symbols["class"]
    assert "def method_one(self, arg1):" in symbols["function"]
    assert "async def top_level_async_func():" in symbols["function"]

def test_extract_javascript_symbols():
    content = """
import React from 'react';
export class MyComponent extends React.Component {}
function helper() {}
export const arrowFunc = (arg1) => {}
export async function getData() {}
    """
    patterns = LANGUAGE_PATTERNS['javascript']['patterns']
    symbols = _extract_symbols_by_regex(content, patterns)
    assert "import React from 'react';" in symbols["imports"]
    assert "export class MyComponent extends React.Component {}" in symbols["class"]
    assert "function helper() {}" in symbols["function"]
    assert "export const arrowFunc = (arg1) => {}" in symbols["function"]
    assert "export async function getData() {}" in symbols["function"]

def test_build_structure_context(mixed_project):
    os.chdir(mixed_project)
    result = build_context("@structure", {}, mixed_project)
    assert result is not None
    context = result["context"]
    assert "<file_path:api/main.py>" in context
    assert "<file_path:frontend/src/index.js>" in context
    assert "README.md" not in context
    assert "class APIServer:" in context
    assert "async def get_user(id: int) -> User:" in context
    assert "export class App extends React.Component {" in context
    assert "export const arrowFunc = () => {" in context
    assert "Project Structure Outline:" in context