import os
from patchllm.context import build_context, _extract_symbols_by_regex, LANGUAGE_PATTERNS

# --- Unit Tests for Regex Extraction ---

def test_extract_python_symbols():
    """Unit test Python regex patterns."""
    content = """
import os
from .models import User, session
import multi.line.import (
    a, b, c
)

# This is a comment
class MyClass(Parent):
    def method_one(self, arg1):
        pass

async def top_level_async_func():
    pass
    """
    patterns = LANGUAGE_PATTERNS['python']['patterns']
    symbols = _extract_symbols_by_regex(content, patterns)

    assert "import os" in symbols["imports"]
    assert "from .models import User, session" in symbols["imports"]
    assert "class MyClass(Parent):" in symbols["class"]
    assert "def method_one(self, arg1):" in symbols["function"]
    assert "async def top_level_async_func():" in symbols["function"]
    assert len(symbols["imports"]) == 3


def test_extract_javascript_symbols():
    """Unit test JavaScript regex patterns."""
    content = """
import React from 'react';
const { v4: uuidv4 } = require('uuid');

export class MyComponent extends React.Component {
  // A comment
}

function helper() {
  console.log('help');
}

export const arrowFunc = (arg1, arg2) => {
  // implementation
}

export async function getData() {
  // get data
}
    """
    patterns = LANGUAGE_PATTERNS['javascript']['patterns']
    symbols = _extract_symbols_by_regex(content, patterns)

    assert "import React from 'react';" in symbols["imports"]
    assert "const { v4: uuidv4 } = require('uuid');" in symbols["imports"]
    assert "export class MyComponent extends React.Component {" in symbols["class"]
    assert "function helper() {" in symbols["function"]
    assert "export const arrowFunc = (arg1, arg2) => {" in symbols["function"]
    assert "export async function getData() {" in symbols["function"]
    assert len(symbols["function"]) == 3

# --- Integration Test for @structure scope ---

def test_build_structure_context(mixed_project):
    """Test the full @structure scope generation."""
    os.chdir(mixed_project)
    result = build_context("@structure", {}, mixed_project)

    assert result is not None
    context = result["context"]

    # Check for file paths
    assert "<file_path:api/main.py>" in context
    assert "<file_path:api/models.py>" in context
    assert "<file_path:frontend/src/index.js>" in context
    assert "<file_path:frontend/src/utils.ts>" in context
    assert "README.md" not in context

    # Check for Python symbols
    assert "class APIServer:" in context
    assert "async def get_user(id: int) -> User:" in context
    assert "class User(Base):" in context
    assert "from .models import User" in context
    
    # Check for JS/TS symbols
    assert "export class App extends Component {" in context
    assert "export const arrowFunc = () => {" in context
    assert "export async function fetchData(url: string): Promise<any> {" in context
    assert "import React from \"react\";" in context

    # Check that it did NOT pick up the commented out function
    assert "def my_func()" not in context

    # Check for correct formatting
    assert "[imports]" in context
    assert "[symbols]" in context
    assert "Project Structure Outline:" in context