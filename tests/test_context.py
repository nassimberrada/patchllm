import os
import time
import subprocess
import textwrap
from patchllm.context import build_context
from patchllm.utils import load_from_py_file

# --- Static Scope Tests ---

def test_build_context_static_scope(temp_project, temp_scopes_file):
    """Test a basic static scope that includes and excludes files."""
    scopes = load_from_py_file(temp_scopes_file, "scopes")
    
    # Simulate running from the project root, which is critical for relative paths
    os.chdir(temp_project)
    
    # Pass the project's root as the base_path
    result = build_context("base", scopes, temp_project)
    
    assert result is not None
    context = result["context"]
    
    assert "main.py" in context
    assert "utils.py" in context
    assert "test_utils.py" not in context  # Should be excluded
    assert "component.js" not in context  # Should be excluded by extension

def test_build_context_static_search_words(temp_project, temp_scopes_file):
    """Test a static scope with the search_words filter."""
    scopes = load_from_py_file(temp_scopes_file, "scopes")

    # Simulate running from the project root
    os.chdir(temp_project)

    result = build_context("search_scope", scopes, temp_project)
    
    assert result is not None
    context = result["context"]

    assert "main.py" in context  # Contains 'hello'
    assert "utils.py" not in context
    assert "README.md" not in context

# --- Dynamic Scope Tests ---

def test_dynamic_scope_git_staged(git_project):
    """Test @git:staged dynamic scope."""
    # Stage a file
    (git_project / "main.py").write_text("new content")
    subprocess.run(["git", "add", "main.py"], cwd=git_project, check=True)
    
    result = build_context("@git:staged", {}, git_project)
    
    assert result is not None
    context = result["context"]
    
    assert "main.py" in context
    assert "utils.py" not in context

def test_dynamic_scope_git_unstaged(git_project):
    """Test @git:unstaged dynamic scope."""
    (git_project / "utils.py").write_text("unstaged changes")
    
    result = build_context("@git:unstaged", {}, git_project)
    
    assert result is not None
    assert "utils.py" in result["context"]
    assert "main.py" not in result["context"]

def test_dynamic_scope_recent(temp_project):
    """Test @recent dynamic scope."""
    # Make one file more recent to ensure it's picked up
    time.sleep(0.1)
    (temp_project / "main.py").touch()
    
    result = build_context("@recent", {}, temp_project)
    
    assert result is not None
    tree = result["tree"]
    # main.py should be the first one found, but tree is alphabetical
    assert "main.py" in tree
    # Check that it finds at least 5 files by default (project has more)
    assert len(tree.strip().split('\n')) >= 5 # 1 root + at least 4 files

def test_dynamic_scope_search(temp_project):
    """Test @search dynamic scope."""
    result = build_context('@search:"helper_function"', {}, temp_project)
    
    assert result is not None
    context = result["context"]
    assert "utils.py" in context
    assert "test_utils.py" in context
    assert "main.py" not in context

def test_dynamic_scope_error_traceback(temp_project):
    """Test @error dynamic scope."""
    main_py_path = (temp_project / "main.py").as_posix()
    utils_py_path = (temp_project / "utils.py").as_posix()
    
    # Use textwrap.dedent to create a clean, multiline string
    traceback = textwrap.dedent(f'''
        Traceback (most recent call last):
          File "{main_py_path}", line 3, in <module>
            utils.do_stuff()
          File "{utils_py_path}", line 5, in do_stuff
            return 1/0
        ZeroDivisionError: division by zero
    ''').strip()

    # CORRECTED: Build the scope string using concatenation to avoid nested quotes
    scope_string = '@error:"' + traceback + '"'
    result = build_context(scope_string, {}, temp_project)
    
    assert result is not None, "build_context should not return None for a valid traceback"
    context = result["context"]
    assert "main.py" in context
    assert "utils.py" in context
    assert "README.md" not in context

def test_dynamic_scope_related(temp_project):
    """Test @related dynamic scope."""
    result = build_context("@related:utils.py", {}, temp_project)
    
    assert result is not None
    context = result["context"]
    assert "utils.py" in context
    assert "test_utils.py" in context  # Should find the related test file
    assert "main.py" not in context

def test_dynamic_scope_dir(temp_project):
    """Test @dir dynamic scope."""
    result = build_context("@dir:src", {}, temp_project)

    assert result is not None
    context = result["context"]
    assert "component.js" in context
    assert "styles.css" in context
    assert "main.py" not in context