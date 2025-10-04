import glob
import textwrap
import subprocess
import shutil
from pathlib import Path
from rich.console import Console
import re
import os

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

# --- New: Structure Extraction Settings ---
STRUCTURE_EXCLUDE_DIRS = ['.git', '__pycache__', 'node_modules', '.venv', 'dist', 'build']

STRUCTURE_TEMPLATE = textwrap.dedent('''
    Project Structure Outline:
    --------------------------
    {{structure_content}}
''')

LANGUAGE_PATTERNS = {
    'python': {
        'extensions': ['.py'],
        'patterns': [
            ('imports', re.compile(r"^\s*(?:from\s+[\w\.]+\s+)?import\s+[\w\.\*,\s\(\)]+")),
            # CORRECTED: Made wildcards non-greedy to handle complex signatures.
            ('class', re.compile(r"^\s*class\s+.*?:")),
            ('function', re.compile(r"^\s*(?:async\s+)?def\s+.*?\(.*?\).*?:")),
        ]
    },
    'javascript': {
        'extensions': ['.js', '.jsx', '.ts', '.tsx'],
        'patterns': [
            ('imports', re.compile(r"^\s*import\s+.*from\s+.*|^\s*(?:const|let|var)\s+.*?=\s*require\(.*")),
            ('class', re.compile(r"^\s*(?:export\s+)?class\s+\w+.*\{")),
            ('function', re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+\w+\(.*\)|^\s*(?:export\s+)?(?:const|let|var)\s+\w+\s*=\s*(?:async)?\s*\(.*\)\s*=>")),
        ]
    }
}


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

# --- Dynamic Scope Resolution ---

def _run_git_command(command: list[str], base_path: Path) -> list[Path]:
    """Helper to run a git command and return a list of file paths."""
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=True, cwd=base_path
        )
        files = result.stdout.strip().split('\n')
        return [base_path / f for f in files if f]
    except FileNotFoundError:
        console.print("❌ Git not found. Cannot resolve git-based scope.", style="red")
    except subprocess.CalledProcessError:
        # This is often not an error, e.g., no staged files, no conflicts.
        pass
    except Exception as e:
        console.print(f"❌ An error occurred with Git: {e}", style="red")
    return []

def _resolve_recent_files(base_path: Path, count: int = 5) -> list[Path]:
    """Returns a list of the most recently modified files."""
    all_files = filter(Path.is_file, base_path.rglob('*'))
    try:
        sorted_files = sorted(all_files, key=lambda p: p.stat().st_mtime, reverse=True)
        return sorted_files[:count]
    except Exception as e:
        console.print(f"❌ Error finding recent files: {e}", style="red")
        return []

def _resolve_search_files(search_term: str, base_path: Path) -> list[Path]:
    """Finds all files containing the given search term."""
    all_files = find_files(base_path, ["**/*"])
    return filter_files_by_keyword(all_files, [search_term])

def _resolve_error_traceback_files(traceback: str, base_path: Path) -> list[Path]:
    """Parses file paths from a traceback and returns them."""
    # This regex looks for patterns like: File "/path/to/file.py", line 123
    pattern = r'File "([^"]+)"'
    matches = re.findall(pattern, traceback)
    
    files = set()
    for file_str in matches:
        path = Path(file_str)
        # If the path is absolute, use it. Otherwise, resolve it relative to the base path.
        if path.is_absolute():
            files.add(path)
        else:
            files.add((base_path / path).resolve())
            
    return sorted([f for f in files if f.exists()])

def _resolve_directory_files(dir_path_str: str, base_path: Path) -> list[Path]:
    """Gets all files in a specific directory (non-recursively)."""
    dir_path = (base_path / dir_path_str).resolve()
    if not dir_path.is_dir():
        console.print(f"❌ Directory not found for @dir scope: {dir_path}", style="red")
        return []
    return sorted([f for f in dir_path.iterdir() if f.is_file()])

def _resolve_related_files(file_path_str: str, base_path: Path) -> list[Path]:
    """Finds files related to the given file by naming convention."""
    start_path = (base_path / file_path_str).resolve()
    if not start_path.exists():
        console.print(f"❌ File not found for @related scope: {start_path}", style="red")
        return []

    related_files = {start_path}
    stem = start_path.stem
    
    # Common test patterns
    test_variations = [
        start_path.parent / f"test_{stem}{start_path.suffix}",
        base_path / "tests" / f"test_{stem}{start_path.suffix}",
        start_path.parent.parent / "tests" / start_path.parent.name / f"test_{stem}{start_path.suffix}"
    ]
    # Sibling files (e.g., .js, .css, .html)
    sibling_exts = ['.css', '.js', '.html', '.scss', '.py', '.md']
    for ext in sibling_exts:
        if ext != start_path.suffix:
            related_files.add(start_path.with_suffix(ext))
    
    for path in test_variations:
        if path.exists():
            related_files.add(path)
            
    return sorted(list(related_files))


def _format_context(file_paths: list[Path], urls: list[str], base_path: Path) -> dict | None:
    """Helper to format the final context string from a list of files and URLs."""
    source_tree_str = generate_source_tree(base_path, file_paths)
    
    file_contents = []
    for file_path in file_paths:
        try:
            display_path = file_path.as_posix()
            content = file_path.read_text(encoding='utf-8')
            file_contents.append(f"<file_path:{display_path}>\n```\n{content}\n```")
        except Exception as e:
            console.print(f"⚠️  Could not read file {file_path}: {e}", style="yellow")

    files_content_str = "\n\n".join(file_contents)
    url_contents_str = fetch_and_process_urls(urls)

    final_context = BASE_TEMPLATE.replace("{{source_tree}}", source_tree_str)
    final_context = final_context.replace("{{url_contents}}", url_contents_str)
    final_context = final_context.replace("{{files_content}}", files_content_str)
    
    return {"tree": source_tree_str, "context": final_context}

# --- Structure Context Functions ---
def _extract_symbols_by_regex(content: str, lang_patterns: list) -> dict:
    """Extracts symbols from content using a list of regex patterns."""
    symbols = {"imports": [], "class": [], "function": []}
    for line in content.splitlines():
        for symbol_type, pattern in lang_patterns:
            if pattern.match(line):
                symbols[symbol_type].append(line.strip())
                break # A line can only be one type of symbol
    return symbols

def _build_structure_context(base_path: Path) -> dict | None:
    """Builds a context by extracting symbols from all project files."""
    all_files = []
    for p in base_path.rglob('*'):
        if any(part in STRUCTURE_EXCLUDE_DIRS for part in p.parts):
            continue
        if p.is_file() and p.suffix.lower() not in DEFAULT_EXCLUDE_EXTENSIONS:
            all_files.append(p)
    
    structure_outputs = []
    for file_path in sorted(all_files):
        lang = None
        for lang_name, config in LANGUAGE_PATTERNS.items():
            if file_path.suffix in config['extensions']:
                lang = lang_name
                break
        
        if lang:
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                symbols = _extract_symbols_by_regex(content, LANGUAGE_PATTERNS[lang]['patterns'])
                
                if any(symbols.values()):
                    rel_path = file_path.relative_to(base_path)
                    output = [f"<file_path:{rel_path.as_posix()}>"]
                    if symbols['imports']:
                        output.append("[imports]")
                        output.extend([f"- {s}" for s in symbols['imports']])
                    if symbols['class'] or symbols['function']:
                         output.append("[symbols]")
                         output.extend([f"- {s}" for s in symbols['class']])
                         output.extend([f"- {s}" for s in symbols['function']])
                    structure_outputs.append("\n".join(output))

            except Exception as e:
                console.print(f"⚠️ Could not process {file_path} for structure view: {e}", style="yellow")

    if not structure_outputs:
        return None

    final_content = "\n\n".join(structure_outputs)
    final_context = STRUCTURE_TEMPLATE.replace("{{structure_content}}", final_content)
    
    return {"tree": "Project structure view", "context": final_context}


# --- Main Context Building Function ---

def build_context_from_files(file_paths: list[Path], base_path: Path) -> dict | None:
    """
    Builds the context string directly from a provided list of file paths.
    """
    if not file_paths:
        console.print("\n⚠️  No files were provided to build the context.", style="yellow")
        return None
    
    return _format_context(file_paths, [], base_path)


def build_context(scope_name: str, scopes: dict, base_path: Path) -> dict | None:
    """
    Builds the context string from files, handling both static and dynamic scopes.
    """
    if scope_name == "@structure":
        return _build_structure_context(base_path)

    relevant_files = []
    urls = []

    if scope_name.startswith('@'):
        console.print(f"Resolving dynamic scope: [bold cyan]{scope_name}[/bold cyan]")
        
        if scope_name.startswith('@error:"') and scope_name.endswith('"'):
            traceback_content = scope_name[len('@error:"'):-1]
            relevant_files = _resolve_error_traceback_files(traceback_content, base_path)
        else:
            search_match = re.match(r'@search:"([^"]+)"', scope_name)
            related_match = re.match(r'@related:(.+)', scope_name)
            dir_match = re.match(r'@dir:(.+)', scope_name)
            branch_match = re.match(r'@git:branch(?::(.+))?', scope_name)

            if search_match:
                relevant_files = _resolve_search_files(search_match.group(1), base_path)
            elif related_match:
                relevant_files = _resolve_related_files(related_match.group(1).strip(), base_path)
            elif dir_match:
                relevant_files = _resolve_directory_files(dir_match.group(1).strip(), base_path)
            elif branch_match:
                base_branch = branch_match.group(1) or os.environ.get("GIT_BASE_BRANCH", "main")
                command = ["git", "diff", "--name-only", f"{base_branch}...HEAD"]
                relevant_files = _run_git_command(command, base_path)
            
            elif scope_name == "@git":
                relevant_files = _run_git_command(["git", "diff", "--name-only", "--cached"], base_path)
            elif scope_name == "@git:staged":
                relevant_files = _run_git_command(["git", "diff", "--name-only", "--cached"], base_path)
            elif scope_name == "@git:unstaged":
                relevant_files = _run_git_command(["git", "diff", "--name-only"], base_path)
            elif scope_name == "@git:lastcommit":
                relevant_files = _run_git_command(["git", "show", "--pretty=format:", "--name-only", "HEAD"], base_path)
            elif scope_name == "@git:conflicts":
                relevant_files = _run_git_command(["git", "diff", "--name-only", "--diff-filter=U"], base_path)
            elif scope_name == "@recent":
                relevant_files = _resolve_recent_files(base_path)
            else:
                console.print(f"❌ Unknown or invalid dynamic scope '{scope_name}'.", style="red")
                return None
    else:
        scope = scopes.get(scope_name)
        if not scope:
            console.print(f"❌ Static scope '{scope_name}' not found in scopes file.", style="red")
            return None
        
        base_path = Path(scope.get("path", ".")).resolve()
        include_patterns = scope.get("include_patterns", [])
        exclude_patterns = scope.get("exclude_patterns", [])
        search_words = scope.get("search_words", [])
        urls = scope.get("urls", [])
        relevant_files = find_files(base_path, include_patterns, exclude_patterns)
        if search_words:
            relevant_files = filter_files_by_keyword(relevant_files, search_words)

    # --- Common Filtering and Formatting ---
    if not relevant_files and not urls:
        console.print("\n⚠️  No files or URLs matched the specified criteria.", style="yellow")
        return None

    exclude_extensions = scopes.get(scope_name, {}).get("exclude_extensions", DEFAULT_EXCLUDE_EXTENSIONS)
    count_before_ext = len(relevant_files)
    norm_ext = {ext.lower() for ext in exclude_extensions}
    relevant_files = [p for p in relevant_files if p.suffix.lower() not in norm_ext]
    if count_before_ext > len(relevant_files):
        console.print(f"Filtered {count_before_ext - len(relevant_files)} files by extension.", style="cyan")

    if not relevant_files and not urls:
        console.print("\n⚠️  No files left after filtering.", style="yellow")
        return None

    return _format_context(relevant_files, urls, base_path)