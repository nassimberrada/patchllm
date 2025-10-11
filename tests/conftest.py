import pytest
import subprocess
import textwrap
from pathlib import Path

@pytest.fixture
def temp_project(tmp_path):
    """Creates a temporary project structure for testing."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    (project_dir / "main.py").write_text("import utils\n\ndef hello():\n    print('hello')")
    (project_dir / "utils.py").write_text("def helper_function():\n    return 1")
    (project_dir / "README.md").write_text("# Test Project")

    src_dir = project_dir / "src"
    src_dir.mkdir()
    (src_dir / "component.js").write_text("console.log('component');")
    (src_dir / "styles.css").write_text("body { color: red; }")

    tests_dir = project_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_utils.py").write_text("from .. import utils\n\ndef test_helper():\n    assert utils.helper_function() == 1")
    
    (project_dir / "data.log").write_text("some log data")
    (project_dir / "logo.png").write_bytes(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01\xe2!\xbc\x33\x00\x00\x00\x00IEND\xaeB`\x82')

    return project_dir

@pytest.fixture
def git_project(temp_project):
    """Initializes the temp_project as a Git repository."""
    subprocess.run(["git", "init"], cwd=temp_project, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_project, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_project, check=True)
    subprocess.run(["git", "add", "."], cwd=temp_project, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=temp_project, check=True, capture_output=True)
    return temp_project

@pytest.fixture
def temp_scopes_file(tmp_path):
    """Creates a temporary scopes.py file for testing."""
    scopes_content = """
scopes = {
    'base': {
        'path': '.',
        'include_patterns': ['**/*.py'],
        'exclude_patterns': ['tests/**'],
    },
    'search_scope': {
        'path': '.',
        'include_patterns': ['**/*'],
        'search_words': ['hello']
    },
    'js_and_css': {
        'path': 'src',
        'include_patterns': ['**/*.js', '**/*.css']
    }
}
"""
    scopes_file = tmp_path / "scopes.py"
    scopes_file.write_text(scopes_content)
    return scopes_file

@pytest.fixture
def temp_recipes_file(tmp_path):
    """Creates a temporary recipes.py file for testing."""
    recipes_content = """
recipes = {
    "add_tests": "Please write comprehensive pytest unit tests for the functions in the provided file.",
    "add_docs": "Generate Google-style docstrings for all public functions and classes.",
}
"""
    recipes_file = tmp_path / "recipes.py"
    recipes_file.write_text(recipes_content)
    return recipes_file

@pytest.fixture
def mixed_project(tmp_path):
    """Creates a project with both Python and JS files for structure testing."""
    proj_dir = tmp_path / "mixed_project"
    
    py_api_dir = proj_dir / "api"
    py_api_dir.mkdir(parents=True)
    (py_api_dir / "main.py").write_text(textwrap.dedent("""
        import os
        from .models import User
        class APIServer:
            def start(self): pass
        async def get_user(id: int) -> User:
            # A comment
            return User()
        """))
    (py_api_dir / "models.py").write_text(textwrap.dedent("""
        from db import Base
        class User(Base): pass
        """))

    js_src_dir = proj_dir / "frontend" / "src"
    js_src_dir.mkdir(parents=True)
    (js_src_dir / "index.js").write_text(textwrap.dedent("""
        import React from "react";
        export class App extends React.Component { render() { return <h1>Hello</h1>; } }
        export const arrowFunc = () => { console.log('test'); }
        """))
    (js_src_dir / "utils.ts").write_text(textwrap.dedent("""
        export async function fetchData(url: string): Promise<any> { }
        """))
    
    (proj_dir / "README.md").write_text("# Mixed Project")

    return proj_dir