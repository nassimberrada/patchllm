import importlib.util
from pathlib import Path
import pprint
from rich.console import Console

console = Console()

def load_from_py_file(file_path, dict_name):
    """Dynamically loads a dictionary from a Python file."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"The file '{path}' was not found.")
    
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None:
         raise ImportError(f"Could not load spec for module at '{path}'")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    dictionary = getattr(module, dict_name, None)
    if not isinstance(dictionary, dict):
        raise TypeError(f"The file '{path}' must contain a dictionary named '{dict_name}'.")
    
    return dictionary

def write_scopes_to_file(file_path, scopes_dict):
    """Writes the scopes dictionary back to a Python file."""
    try:
        path = Path(file_path)
        with open(path, "w", encoding="utf-8") as f:
            f.write("scopes = ")
            f.write(pprint.pformat(scopes_dict, indent=4))
            f.write("\n")
        console.print(f"✅ Successfully updated '{path}'.", style="green")
    except Exception as e:
        console.print(f"❌ Failed to write to '{path}': {e}", style="red")