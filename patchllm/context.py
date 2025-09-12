import glob
import textwrap
import subprocess
import shutil
from pathlib import Path
from rich.console import Console

console = Console()

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
    {{url_contents}}
    Relevant Files:
    ---------------
    {{files_content}}
''')

URL_CONTENT_TEMPLATE = textwrap.dedent('''
    URL Contents:
    -------------
    {{content}}
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
            if any(word in file_path.read_text(encoding='utf-8', errors='ignore') for word in search_words):
                matching_files.append(file_path)
        except Exception as e:
            console.print(f"⚠️  Could not read {file_path} for keyword search: {e}", style="yellow")
    return matching_files


def generate_source_tree(base_path: Path, file_paths: list[Path]) -> str:
    """Generates a string representation of the file paths as a tree."""
    if not file_paths:
        return "No files found matching the criteria."
    
    tree = {}
    for path in file_paths:
        try:
            rel_path = path.relative_to(base_path)
        except ValueError:
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


def fetch_and_process_urls(urls: list[str]) -> str:
    """Downloads and converts a list of URLs to text, returning a formatted string."""
    if not urls:
        return ""

    try:
        import html2text
    except ImportError:
        console.print("⚠️  To use the URL feature, please install the required extras:", style="yellow")
        console.print("   pip install patchllm[url]", style="cyan")
        return ""

    downloader = None
    if shutil.which("curl"):
        downloader = "curl"
    elif shutil.which("wget"):
        downloader = "wget"

    if not downloader:
        console.print("⚠️  Cannot fetch URL content: 'curl' or 'wget' not found in PATH.", style="yellow")
        return ""

    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    
    all_url_contents = []

    console.print("\n--- Fetching URL Content... ---", style="bold")
    for url in urls:
        try:
            console.print(f"Fetching [cyan]{url}[/cyan]...")
            if downloader == "curl":
                command = ["curl", "-s", "-L", url]
            else: # wget
                command = ["wget", "-q", "-O", "-", url]

            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=15)
            html_content = result.stdout
            text_content = h.handle(html_content)
            all_url_contents.append(f"<url_content:{url}>\n```\n{text_content}\n```")

        except subprocess.CalledProcessError as e:
            console.print(f"❌ Failed to fetch {url}: {e.stderr}", style="red")
        except subprocess.TimeoutExpired:
            console.print(f"❌ Failed to fetch {url}: Request timed out.", style="red")
        except Exception as e:
            console.print(f"❌ An unexpected error occurred while fetching {url}: {e}", style="red")

    if not all_url_contents:
        return ""
    
    content_str = "\n\n".join(all_url_contents)
    return URL_CONTENT_TEMPLATE.replace("{{content}}", content_str)

# --- Main Context Building Function ---

def build_context(config: dict) -> dict | None:
    """
    Builds the context string from files specified in the config.

    Args:
        config (dict): The configuration for file searching.

    Returns:
        dict: A dictionary with the source tree and formatted context, or None.
    """
    base_path = Path(config.get("path", ".")).resolve()
    
    include_patterns = config.get("include_patterns", [])
    exclude_patterns = config.get("exclude_patterns", [])
    exclude_extensions = config.get("exclude_extensions", DEFAULT_EXCLUDE_EXTENSIONS)
    search_words = config.get("search_words", [])
    urls = config.get("urls", [])

    # Step 1: Find files
    relevant_files = find_files(base_path, include_patterns, exclude_patterns)

    # Step 2: Filter by extension
    count_before_ext = len(relevant_files)
    norm_ext = {ext.lower() for ext in exclude_extensions}
    relevant_files = [p for p in relevant_files if p.suffix.lower() not in norm_ext]
    if count_before_ext > len(relevant_files):
        console.print(f"Filtered {count_before_ext - len(relevant_files)} files by extension.", style="cyan")

    # Step 3: Filter by keyword
    if search_words:
        count_before_kw = len(relevant_files)
        relevant_files = filter_files_by_keyword(relevant_files, search_words)
        console.print(f"Filtered {count_before_kw - len(relevant_files)} files by keyword search.", style="cyan")

    if not relevant_files and not urls:
        console.print("\n⚠️  No files or URLs matched the specified criteria.", style="yellow")
        return None

    # Generate source tree and file content blocks
    source_tree_str = generate_source_tree(base_path, relevant_files)
    
    file_contents = []
    for file_path in relevant_files:
        try:
            display_path = file_path.as_posix()
            content = file_path.read_text(encoding='utf-8')
            file_contents.append(f"<file_path:{display_path}>\n```\n{content}\n```")
        except Exception as e:
            console.print(f"⚠️  Could not read file {file_path}: {e}", style="yellow")

    files_content_str = "\n\n".join(file_contents)

    # Fetch and process URL contents
    url_contents_str = fetch_and_process_urls(urls)

    # Assemble the final context using the base template
    final_context = BASE_TEMPLATE.replace("{{source_tree}}", source_tree_str)
    final_context = final_context.replace("{{url_contents}}", url_contents_str)
    final_context = final_context.replace("{{files_content}}", files_content_str)
    
    return {"tree": source_tree_str, "context": final_context}