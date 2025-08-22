import importlib.util
from pathlib import Path

def load_from_py_file(file_path, dict_name):
    """Dynamically loads a dictionary from a Python file."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"The file '{path}' was not found.")
    
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    dictionary = getattr(module, dict_name, None)
    if not isinstance(dictionary, dict):
        raise TypeError(f"The file '{path}' must contain a dictionary named '{dict_name}'.")
    
    return dictionary