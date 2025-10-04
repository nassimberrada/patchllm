import pytest
from unittest.mock import patch
from patchllm.cli.entrypoint import main
from patchllm.utils import load_from_py_file, write_scopes_to_file

def run_main_with_args(args, expect_exit=False):
    with patch('sys.argv', ['patchllm'] + args):
        if expect_exit:
            with pytest.raises(SystemExit):
                main()
        else:
            main()

def test_add_scope(tmp_path):
    scopes_file = tmp_path / "scopes.py"
    write_scopes_to_file(scopes_file, {})
    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': scopes_file.as_posix()}):
        run_main_with_args(["--add-scope", "new_scope"])
    scopes = load_from_py_file(scopes_file, "scopes")
    assert "new_scope" in scopes
    assert scopes["new_scope"]["path"] == "."

def test_remove_scope(temp_scopes_file):
    scopes_before = load_from_py_file(temp_scopes_file, "scopes")
    assert "base" in scopes_before
    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
        run_main_with_args(["--remove-scope", "base"])
    scopes_after = load_from_py_file(temp_scopes_file, "scopes")
    assert "base" not in scopes_after

def test_update_scope(temp_scopes_file):
    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
        run_main_with_args(["--update-scope", "base", "path='/new/path'"])
    scopes = load_from_py_file(temp_scopes_file, "scopes")
    assert scopes["base"]["path"] == "/new/path"

def test_update_scope_add_new_key(temp_scopes_file):
    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
        run_main_with_args(["--update-scope", "base", "new_key=True"])
    scopes = load_from_py_file(temp_scopes_file, "scopes")
    assert scopes["base"]["new_key"] is True

def test_update_scope_invalid_value(temp_scopes_file, capsys):
    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
        run_main_with_args(["--update-scope", "base", "path=unquoted"])
    captured = capsys.readouterr()
    assert "Error parsing update values" in captured.out