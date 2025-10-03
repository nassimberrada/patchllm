import pytest
import subprocess
from pathlib import Path

@pytest.fixture
def temp_project(tmp_path):
    """Creates a temporary project structure for testing."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    # Create some files
    (project_dir / "main.py").write_text("import utils\n\ndef hello():\n    print('hello')")
    (project_dir / "utils.py").write_text("def helper_function():\n    return 1")
    (project_dir / "README.md").write_text("# Test Project")

    # Create a subdirectory
    src_dir = project_dir / "src"
    src_dir.mkdir()
    (src_dir / "component.js").write_text("console.log('component');")
    (src_dir / "styles.css").write_text("body { color: red; }")

    # Create a test file
    tests_dir = project_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_utils.py").write_text("from .. import utils\n\ndef test_helper():\n    assert utils.helper_function() == 1")
    
    # Create a file with a common extension to be excluded
    (project_dir / "data.log").write_text("some log data")

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
