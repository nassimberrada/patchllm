import os
import time
import subprocess
import textwrap
import pytest
import base64
# --- MODIFICATION: Changed to absolute imports ---
from patchllm.scopes.builder import build_context
from patchllm.utils import load_from_py_file
from patchllm.scopes.helpers import _format_context

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

def test_format_context_with_image(temp_project):
    """Tests that _format_context correctly processes both text and image files."""
    os.chdir(temp_project)
    text_file = temp_project / "main.py"
    image_file = temp_project / "logo.png"
    
    all_files = [text_file, image_file]
    
    result = _format_context(all_files, [], temp_project)
    
    assert result is not None
    
    # Check text context
    assert "<file_path:" in result["context"]
    assert "main.py" in result["context"]
    assert "<file_path:" + image_file.as_posix() not in result["context"] # Image content shouldn't be in text context
    
    # Check image data
    assert "images" in result
    assert len(result["images"]) == 1
    image_data = result["images"][0]
    assert image_data["path"] == image_file
    assert image_data["mime_type"] == "image/png"
    
    # Check if base64 content is valid
    try:
        base64.b64decode(image_data["content_base64"])
    except Exception:
        pytest.fail("Image content is not valid base64")

    # Check files list
    assert "files" in result
    assert len(result["files"]) == 2
    assert text_file in result["files"]
    assert image_file in result["files"]

def test_build_context_static_scope_with_dynamic_patterns(git_project):
    """
    Tests that a static scope can successfully include and exclude files
    using dynamic scopes (@-prefixed) as patterns.
    """
    # 1. Setup: Define the scopes dictionary directly
    scopes = {
        'dynamic_in_static': {
            'path': '.',
            'include_patterns': ['@git:staged', 'src/*.css'],
            'exclude_patterns': ['**/README.md', '@git:unstaged']
        }
    }
    os.chdir(git_project)
    
    # 2. Action: Stage one file, leave another unstaged
    (git_project / "main.py").write_text("new staged content")
    subprocess.run(["git", "add", "main.py"], cwd=git_project, check=True)

    (git_project / "utils.py").write_text("new unstaged content") # This should be excluded
    
    # 3. Build context
    result = build_context("dynamic_in_static", scopes, git_project)

    # 4. Assertions
    assert result is not None
    files = result["files"]
    file_names = {f.name for f in files}

    assert "main.py" in file_names      # Included via @git:staged
    assert "styles.css" in file_names   # Included via glob
    assert "README.md" not in file_names # Excluded via glob
    assert "utils.py" not in file_names   # Excluded via @git:unstaged