import os
import time
import subprocess
import textwrap
from patchllm.scopes.builder import build_context
from patchllm.utils import load_from_py_file

# --- Static Scope Tests ---

def test_build_context_static_scope(temp_project, temp_scopes_file):
    scopes = load_from_py_file(temp_scopes_file, "scopes")
    os.chdir(temp_project)
    result = build_context("base", scopes, temp_project)
    assert result is not None
    context = result["context"]
    assert "main.py" in context
    assert "utils.py" in context
    assert "test_utils.py" not in context
    assert "component.js" not in context

def test_build_context_static_search_words(temp_project, temp_scopes_file):
    scopes = load_from_py_file(temp_scopes_file, "scopes")
    os.chdir(temp_project)
    result = build_context("search_scope", scopes, temp_project)
    assert result is not None
    context = result["context"]
    assert "main.py" in context
    assert "utils.py" not in context
    assert "README.md" not in context

# --- Dynamic Scope Tests ---

def test_dynamic_scope_git_staged(git_project):
    (git_project / "main.py").write_text("new content")
    subprocess.run(["git", "add", "main.py"], cwd=git_project, check=True)
    result = build_context("@git:staged", {}, git_project)
    assert result is not None
    context = result["context"]
    assert "main.py" in context
    assert "utils.py" not in context

def test_dynamic_scope_git_unstaged(git_project):
    (git_project / "utils.py").write_text("unstaged changes")
    result = build_context("@git:unstaged", {}, git_project)
    assert result is not None
    assert "utils.py" in result["context"]
    assert "main.py" not in result["context"]

def test_dynamic_scope_recent(temp_project):
    time.sleep(0.1)
    (temp_project / "main.py").touch()
    result = build_context("@recent", {}, temp_project)
    assert result is not None
    tree = result["tree"]
    assert "main.py" in tree
    assert len(tree.strip().split('\n')) >= 5

def test_dynamic_scope_search(temp_project):
    os.chdir(temp_project)
    result = build_context('@search:"helper_function"', {}, temp_project)
    assert result is not None
    context = result["context"]
    assert "utils.py" in context
    assert "test_utils.py" in context
    assert "main.py" not in context

def test_dynamic_scope_error_traceback(temp_project):
    main_py_path = (temp_project / "main.py").as_posix()
    utils_py_path = (temp_project / "utils.py").as_posix()
    traceback = textwrap.dedent(f'''
        Traceback (most recent call last):
          File "{main_py_path}", line 3, in <module>
          File "{utils_py_path}", line 5, in do_stuff
        ZeroDivisionError: division by zero
    ''').strip()
    scope_string = '@error:"' + traceback + '"'
    result = build_context(scope_string, {}, temp_project)
    assert result is not None
    context = result["context"]
    assert "main.py" in context
    assert "utils.py" in context
    assert "README.md" not in context

def test_dynamic_scope_related(temp_project):
    os.chdir(temp_project)
    result = build_context("@related:utils.py", {}, temp_project)
    assert result is not None
    context = result["context"]
    assert "utils.py" in context
    assert "test_utils.py" in context
    assert "main.py" not in context

def test_dynamic_scope_dir(temp_project):
    os.chdir(temp_project)
    result = build_context("@dir:src", {}, temp_project)
    assert result is not None
    context = result["context"]
    assert "component.js" in context
    assert "styles.css" in context
    assert "main.py" not in context