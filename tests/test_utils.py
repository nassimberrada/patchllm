from patchllm.utils import load_from_py_file, write_scopes_to_file
import pytest

def test_load_from_py_file_success(temp_scopes_file):
    scopes = load_from_py_file(temp_scopes_file, "scopes")
    assert isinstance(scopes, dict)
    assert "base" in scopes

def test_load_from_py_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_from_py_file(tmp_path / "nonexistent.py", "scopes")

def test_load_from_py_file_dict_not_found(tmp_path):
    p = tmp_path / "invalid_scopes.py"
    p.write_text("my_scopes = {}")
    with pytest.raises(TypeError):
        load_from_py_file(p, "scopes")

def test_load_from_py_file_not_a_dict(tmp_path):
    p = tmp_path / "invalid_type.py"
    p.write_text("scopes = [1, 2, 3]")
    with pytest.raises(TypeError):
        load_from_py_file(p, "scopes")

def test_write_scopes_to_file(tmp_path):
    scopes_file = tmp_path / "output_scopes.py"
    scopes_data = {"test_scope": {"path": "/tmp"}}
    write_scopes_to_file(scopes_file, scopes_data)
    assert scopes_file.exists()
    loaded_scopes = load_from_py_file(scopes_file, "scopes")
    assert loaded_scopes == scopes_data