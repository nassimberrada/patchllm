import pytest
from unittest.mock import patch
from patchllm.main import main, write_scopes_to_file
from patchllm.utils import load_from_py_file

def run_main_with_args(args, expect_exit=False):
    """Helper to run the main function with a list of arguments."""
    with patch('sys.argv', ['patchllm'] + args):
        if expect_exit:
            with pytest.raises(SystemExit):
                main()
        else:
            main()

def test_add_scope(tmp_path):
    """Test the --add-scope command."""
    scopes_file = tmp_path / "scopes.py"
    write_scopes_to_file(scopes_file, {})
    
    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': scopes_file.as_posix()}):
        run_main_with_args(["--add-scope", "new_scope"])
    
    scopes = load_from_py_file(scopes_file, "scopes")
    assert "new_scope" in scopes
    assert scopes["new_scope"]["path"] == "."

def test_remove_scope(temp_scopes_file):
    """Test the --remove-scope command."""
    scopes_before = load_from_py_file(temp_scopes_file, "scopes")
    assert "base" in scopes_before
    
    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
        run_main_with_args(["--remove-scope", "base"])

    scopes_after = load_from_py_file(temp_scopes_file, "scopes")
    assert "base" not in scopes_after

def test_update_scope(temp_scopes_file):
    """Test the --update-scope command."""
    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
        run_main_with_args([
            "--update-scope",
            "base",
            "path='/new/path'",
            "include_patterns=['**/*.js']"
        ])
    
    scopes = load_from_py_file(temp_scopes_file, "scopes")
    assert scopes["base"]["path"] == "/new/path"
    assert scopes["base"]["include_patterns"] == ["**/*.js"]

def test_update_scope_add_new_key(temp_scopes_file, capsys):
    """Test that updating a scope can add a new key."""
    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
        run_main_with_args([
            "--update-scope",
            "base",
            "new_key=True"
        ])

    scopes = load_from_py_file(temp_scopes_file, "scopes")
    assert scopes["base"]["new_key"] is True

    captured = capsys.readouterr()
    assert "Key 'new_key' not found in scope" in captured.out

def test_update_scope_invalid_value(temp_scopes_file, capsys):
    """Test graceful failure when update value is not a valid literal."""
    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
        run_main_with_args(["--update-scope", "base", "path=unquoted_string"])

    captured = capsys.readouterr()
    assert "Error parsing update values" in captured.out