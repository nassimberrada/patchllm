import os
import glob
import textwrap
import sys
from pathlib import Path

# --- Default Settings & Templates ---

DEFAULT_EXCLUDE_EXTENSIONS = [
    # General
    ".log", ".lock", ".env", ".bak", ".tmp", ".swp", ".swo", ".db", ".sqlite3",
    # Python
    ".pyc", ".pyo", ".pyd",
    # JS/Node
    ".next", ".svelte-kit",
    # OS-specific
    ".DS_Store",
    # Media/Binary files
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".mp3", ".mp4", ".mov", ".avi", ".pdf",
    ".o", ".so", ".dll", ".exe",
    # Unity specific
    ".meta",
]

BASE_TEMPLATE = textwrap.dedent('''
    Source Tree:
    ------------
    ```
    {{source_tree}}
    ```

    Relevant Files:
    ---------------
    {{files_content}}
''')

# --- Helper Functions (File Discovery, Filtering, Tree Generation) ---

def find_files(base_path: Path, include_patterns: list[str], exclude_patterns: list[str] | None = None) -> list[Path]:
    """Finds all files using glob patterns, handling both relative and absolute paths."""
    if exclude_patterns is None:
        exclude_patterns = []

    def _get_files_from_patterns(patterns: list[str]) -> set[Path]:
        """Helper to process a list of glob patterns and return matching file paths."""
        files = set()
        for pattern_str in patterns:
            pattern_path = Path(pattern_str)
            # If the pattern is absolute, use it as is. Otherwise, join it with the base_path.
            search_path = pattern_path if pattern_path.is_absolute() else base_path / pattern_path
            
            for match in glob.glob(str(search_path), recursive=True):
                path_obj = Path(match).resolve()
                if path_obj.is_file():
                    files.add(path_obj)
        return files

    included_files = _get_files_from_patterns(include_patterns)
    excluded_files = _get_files_from_patterns(exclude_patterns)

    return sorted(list(included_files - excluded_files))


def filter_files_by_keyword(file_paths: list[Path], search_words: list[str]) -> list[Path]:
    """Returns files from a list that contain any of the specified search words."""
    if not search_words:
        return file_paths
    
    matching_files = []
    for file_path in file_paths:
        try:
            # Using pathlib's read_text for cleaner code
            if any(word in file_path.read_text(encoding='utf-8', errors='ignore') for word in search_words):
                matching_files.append(file_path)
        except Exception as e:
            print(f"Warning: Could not read {file_path} for keyword search: {e}", file=sys.stderr)
    return matching_files


def generate_source_tree(base_path: Path, file_paths: list[Path]) -> str:
    """Generates a string representation of the file paths as a tree."""
    if not file_paths:
        return "No files found matching the criteria."
    
    tree = {}
    for path in file_paths:
        try:
            # Create a path relative to the intended base_path for the tree structure
            rel_path = path.relative_to(base_path)
        except ValueError:
            # This occurs if a file (from an absolute pattern) is outside the base_path.
            # In this case, we use the absolute path as a fallback.
            rel_path = path
            
        level = tree
        for part in rel_path.parts:
            level = level.setdefault(part, {})

    def _format_tree(tree_dict, indent=""):
        lines = []
        items = sorted(tree_dict.items(), key=lambda i: (not i[1], i[0]))
        for i, (name, node) in enumerate(items):
            last = i == len(items) - 1
            connector = "└── " if last else "├── "
            lines.append(f"{indent}{connector}{name}")
            if node:
                new_indent = indent + ("    " if last else "│   ")
                lines.extend(_format_tree(node, new_indent))
        return lines

    return f"{base_path.name}\n" + "\n".join(_format_tree(tree))


# --- Main Context Building Function ---

def build_context(config: dict) -> dict | None:
    """
    Builds the context string from files specified in the config.

    Args:
        config (dict): The configuration for file searching.

    Returns:
        dict: A dictionary with the source tree and formatted context, or None.
    """
    # Resolve the base path immediately to get a predictable absolute path.
    base_path = Path(config.get("path", ".")).resolve()
    
    include_patterns = config.get("include_patterns", [])
    exclude_patterns = config.get("exclude_patterns", [])
    exclude_extensions = config.get("exclude_extensions", DEFAULT_EXCLUDE_EXTENSIONS)
    search_words = config.get("search_words", [])

    # Step 1: Find files
    relevant_files = find_files(base_path, include_patterns, exclude_patterns)

    # Step 2: Filter by extension
    count_before_ext = len(relevant_files)
    norm_ext = {ext.lower() for ext in exclude_extensions}
    relevant_files = [p for p in relevant_files if p.suffix.lower() not in norm_ext]
    if count_before_ext > len(relevant_files):
        print(f"Filtered {count_before_ext - len(relevant_files)} files by extension.")

    # Step 3: Filter by keyword
    if search_words:
        count_before_kw = len(relevant_files)
        relevant_files = filter_files_by_keyword(relevant_files, search_words)
        print(f"Filtered {count_before_kw - len(relevant_files)} files by keyword search.")

    if not relevant_files:
        print("\nNo files matched the specified criteria.")
        return None

    print(f"\nFinal count of relevant files: {len(relevant_files)}.")

    # Generate source tree and file content blocks
    source_tree_str = generate_source_tree(base_path, relevant_files)
    
    file_contents = []
    for file_path in relevant_files:
        try:
            display_path = file_path.as_posix()
            content = file_path.read_text(encoding='utf-8')
            file_contents.append(f"<file_path:{display_path}>\n```\n{content}\n```")
        except Exception as e:
            print(f"Warning: Could not read file {file_path}: {e}", file=sys.stderr)

    files_content_str = "\n\n".join(file_contents)

    # Assemble the final context using the base template
    final_context = BASE_TEMPLATE.replace("{{source_tree}}", source_tree_str)
    final_context = final_context.replace("{{files_content}}", files_content_str)
    
    return {"tree": source_tree_str, "context": final_context}