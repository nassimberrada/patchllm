from patchllm.utils import load_from_py_file
import pytest

def test_load_from_py_file_success(temp_scopes_file):
    """Test loading a valid dictionary from a scopes file."""
    scopes = load_from_py_file(temp_scopes_file, "scopes")
    assert isinstance(scopes, dict)
    assert "base" in scopes
    assert scopes["base"]["include_patterns"] == ["**/*.py"]

def test_load_from_py_file_not_found(tmp_path):
    """Test that FileNotFoundError is raised for a non-existent file."""
    with pytest.raises(FileNotFoundError):
        load_from_py_file(tmp_path / "nonexistent.py", "scopes")

def test_load_from_py_file_dict_not_found(tmp_path):
    """Test that TypeError is raised if the dictionary name is not in the file."""
    p = tmp_path / "invalid_scopes.py"
    p.write_text("my_scopes = {}")
    with pytest.raises(TypeError, match="must contain a dictionary named 'scopes'"):
        load_from_py_file(p, "scopes")

def test_load_from_py_file_not_a_dict(tmp_path):
    """Test that TypeError is raised if the found attribute is not a dictionary."""
    p = tmp_path / "invalid_type.py"
    p.write_text("scopes = [1, 2, 3]")
    with pytest.raises(TypeError, match="must contain a dictionary named 'scopes'"):
        load_from_py_file(p, "scopes")
