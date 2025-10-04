import re
import textwrap

# --- Constants for File Exclusion ---

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

STRUCTURE_EXCLUDE_DIRS = ['.git', '__pycache__', 'node_modules', '.venv', 'dist', 'build']

# --- Templates ---

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

STRUCTURE_TEMPLATE = textwrap.dedent('''
    Project Structure Outline:
    --------------------------
    {{structure_content}}
''')

# --- Language Patterns for @structure ---

LANGUAGE_PATTERNS = {
    'python': {
        'extensions': ['.py'],
        'patterns': [
            ('imports', re.compile(r"^\s*(?:from\s+[\w\.]+\s+)?import\s+[\w\.\*,\s\(\)]+")),
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