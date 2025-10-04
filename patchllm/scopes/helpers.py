import glob
import textwrap
import subprocess
import shutil
from pathlib import Path
from rich.console import Console

from .constants import BASE_TEMPLATE, URL_CONTENT_TEMPLATE

console = Console()

def find_files(base_path: Path, include_patterns: list[str], exclude_patterns: list[str] = None) -> list[Path]:
    """Finds all files using glob patterns."""
    exclude_patterns = exclude_patterns or []
    included_files = set()
    for pattern in include_patterns:
        search_path = base_path / pattern
        for match in glob.glob(str(search_path), recursive=True):
            path_obj = Path(match)
            if path_obj.is_file():
                included_files.add(path_obj.resolve())

    excluded_files = set()
    for pattern in exclude_patterns:
        search_path = base_path / pattern
        for match in glob.glob(str(search_path), recursive=True):
            path_obj = Path(match)
            if path_obj.is_file():
                excluded_files.add(path_obj.resolve())
    
    return sorted(list(included_files - excluded_files))

def filter_files_by_keyword(file_paths: list[Path], search_words: list[str]) -> list[Path]:
    """Returns files that contain any of the search words."""
    if not search_words:
        return file_paths
    matching_files = []
    for file_path in file_paths:
        try:
            if any(word in file_path.read_text(encoding='utf-8', errors='ignore') for word in search_words):
                matching_files.append(file_path)
        except Exception:
            pass
    return matching_files

def generate_source_tree(base_path: Path, file_paths: list[Path]) -> str:
    """Generates a string representation of the file paths as a tree."""
    tree = {}
    for path in file_paths:
        try:
            rel_path = path.relative_to(base_path)
            level = tree
            for part in rel_path.parts:
                level = level.setdefault(part, {})
        except ValueError:
            continue

    def _format_tree(tree_dict, indent=""):
        lines = []
        items = sorted(tree_dict.items(), key=lambda i: (not i[1], i[0]))
        for i, (name, node) in enumerate(items):
            connector = "└── " if i == len(items) - 1 else "├── "
            lines.append(f"{indent}{connector}{name}")
            if node:
                new_indent = indent + ("    " if i == len(items) - 1 else "│   ")
                lines.extend(_format_tree(node, new_indent))
        return lines

    return f"{base_path.name}\n" + "\n".join(_format_tree(tree))

def _format_context(file_paths: list[Path], urls: list[str], base_path: Path) -> dict | None:
    """Helper to format the final context string and preserve the file list."""
    source_tree_str = generate_source_tree(base_path, file_paths)
    file_contents = []
    for file_path in file_paths:
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            file_contents.append(f"<file_path:{file_path.as_posix()}>\n```\n{content}\n```")
        except Exception as e:
            console.print(f"⚠️  Could not read file {file_path}: {e}", style="yellow")

    files_content_str = "\n\n".join(file_contents)
    url_contents_str = fetch_and_process_urls(urls)

    final_context = BASE_TEMPLATE.replace("{{source_tree}}", source_tree_str)
    final_context = final_context.replace("{{url_contents}}", url_contents_str)
    final_context = final_context.replace("{{files_content}}", files_content_str)
    
    # --- CORRECTION: Return the original, pristine list of Path objects ---
    return {"tree": source_tree_str, "context": final_context, "files": file_paths}

def fetch_and_process_urls(urls: list[str]) -> str:
    """Downloads and converts a list of URLs to text."""
    if not urls: return ""
    try:
        import html2text
    except ImportError:
        console.print("⚠️  'html2text' is required. Install with: pip install 'patchllm[url]'", style="yellow")
        return ""

    downloader = "curl" if shutil.which("curl") else "wget" if shutil.which("wget") else None
    if not downloader:
        console.print("⚠️ 'curl' or 'wget' not found.", style="yellow")
        return ""

    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    all_url_contents = []

    for url in urls:
        try:
            command = ["curl", "-s", "-L", url] if downloader == "curl" else ["wget", "-q", "-O", "-", url]
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=15)
            text_content = h.handle(result.stdout)
            all_url_contents.append(f"<url_content:{url}>\n```\n{text_content}\n```")
        except Exception as e:
            console.print(f"❌ Failed to fetch {url}: {e}", style="red")

    if not all_url_contents: return ""
    content_str = "\n\n".join(all_url_contents)
    return URL_CONTENT_TEMPLATE.replace("{{content}}", content_str)