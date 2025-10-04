from pathlib import Path
from InquirerPy import prompt
from InquirerPy.validator import EmptyInputValidator
from rich.console import Console
import re

# Import constants from the context module to avoid duplication
# CORRECTED: The typo in DEFAULT_EXCLUDE_EXTENSIONS is now fixed.
from .context import DEFAULT_EXCLUDE_EXTENSIONS, STRUCTURE_EXCLUDE_DIRS

console = Console()

def _build_choices_recursively(current_path: Path, base_path: Path, indent: str = "") -> list[str]:
    """
    Recursively builds a list of formatted strings representing files and folders
    for the InquirerPy checklist, creating a visual tree structure.
    """
    choices = []
    
    # Sort items so directories appear before files
    try:
        # Filter out excluded directories before sorting
        items_to_process = [p for p in current_path.iterdir() if p.name not in STRUCTURE_EXCLUDE_DIRS]
        sorted_items = sorted(items_to_process, key=lambda p: (p.is_file(), p.name.lower()))
    except FileNotFoundError:
        return []

    for i, item in enumerate(sorted_items):
        is_last = i == len(sorted_items) - 1
        connector = "└── " if is_last else "├── "
        
        # Get the path relative to the project's base directory
        relative_item_path = item.relative_to(base_path)

        if item.is_dir():
            choices.append(f"{indent}{connector}📁 {relative_item_path}/")
            new_indent = indent + ("    " if is_last else "│   ")
            choices.extend(_build_choices_recursively(item, base_path, new_indent))
        
        elif item.is_file():
            if item.suffix.lower() not in DEFAULT_EXCLUDE_EXTENSIONS:
                choices.append(f"{indent}{connector}📄 {relative_item_path}")
                
    return choices


def select_files_interactively(base_path: Path) -> list[Path]:
    """
    Displays an interactive checklist with a folder/file tree for the user to select from.
    Returns a list of absolute paths for the selected files, expanding any selected folders.
    """
    choices = _build_choices_recursively(base_path, base_path)
    if not choices:
        console.print("No selectable files or folders found in this project.", style="yellow")
        return []
        
    questions = [
        {
            "type": "checkbox",
            "message": "Select files and/or folders for the context:",
            "choices": choices,
            "validate": EmptyInputValidator("You must select at least one item."),
            "transformer": lambda result: f"{len(result)} item(s) selected",
            "long_instruction": "Press <space> to toggle selection, <enter> to confirm.",
            "border": True,
            "cycle": False, # Better for long lists
        }
    ]
    
    try:
        console.print("\n--- Interactive File Selection ---", style="bold")
        result = prompt(questions, vi_mode=True)
        if not result or not result[0]:
            return []

        # Use a robust regex to capture the path after the icon and space.
        path_extraction_pattern = re.compile(r"[📁📄]\s(.*)")
        
        selected_paths_str = []
        for selection in result[0]:
            match = path_extraction_pattern.search(selection)
            if match:
                selected_paths_str.append(match.group(1))
        
        final_files = set()
        
        for path_str in selected_paths_str:
            full_path = (base_path / path_str).resolve()
            
            if full_path.is_dir():
                # If a directory is selected, recursively find all valid files within it
                for file_in_dir in full_path.rglob('*'):
                    if file_in_dir.is_file() and file_in_dir.suffix.lower() not in DEFAULT_EXCLUDE_EXTENSIONS:
                        final_files.add(file_in_dir)
            elif full_path.is_file():
                # If it's a file, just add it
                final_files.add(full_path)
                
        return sorted(list(final_files))

    except KeyboardInterrupt:
        console.print("\nSelection cancelled by user.", style="yellow")
        return []
    except Exception as e:
        console.print(f"An error occurred during interactive selection: {e}", style="red")
        return []