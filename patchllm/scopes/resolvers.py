import subprocess
from pathlib import Path
import re
import os
from rich.console import Console

console = Console()

def _run_git_command(command: list[str], base_path: Path) -> list[Path]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, cwd=base_path)
        files = result.stdout.strip().split('\n')
        return [base_path / f for f in files if f]
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

def resolve_dynamic_scope(scope_name: str, base_path: Path) -> list[Path]:
    """Resolves a dynamic scope string to a list of file paths."""
    if scope_name.startswith('@error:"') and scope_name.endswith('"'):
        traceback = scope_name[len('@error:"'):-1]
        pattern = r'File "([^"]+)"'
        matches = re.findall(pattern, traceback)
        return sorted([Path(f).resolve() for f in matches if Path(f).exists()])

    search_match = re.match(r'@search:"([^"]+)"', scope_name)
    if search_match:
        from .helpers import find_files, filter_files_by_keyword
        all_files = find_files(base_path, ["**/*"])
        return filter_files_by_keyword(all_files, [search_match.group(1)])

    related_match = re.match(r'@related:(.+)', scope_name)
    if related_match:
        start_path = (base_path / related_match.group(1).strip()).resolve()
        if not start_path.exists(): 
            return []
        related_files = {start_path}
        stem = start_path.stem
        test_variations = [
            start_path.parent / f"test_{stem}{start_path.suffix}",
            base_path / "tests" / f"test_{stem}{start_path.suffix}",
            start_path.parent.parent / "tests" / start_path.parent.name / f"test_{stem}{start_path.suffix}"
        ]
        for path in test_variations:
            if path.exists():
                related_files.add(path)
        sibling_exts = ['.css', '.js', '.html', '.scss', '.py', '.md']
        for ext in sibling_exts:
            if ext != start_path.suffix:
                sibling_path = start_path.with_suffix(ext)
                if sibling_path.exists():
                    related_files.add(sibling_path)
        return sorted(list(related_files))

    dir_match = re.match(r'@dir:(.+)', scope_name)
    if dir_match:
        dir_path = (base_path / dir_match.group(1).strip()).resolve()
        if not dir_path.is_dir(): return []
        return sorted([f for f in dir_path.iterdir() if f.is_file()])

    branch_match = re.match(r'@git:branch(?::(.+))?', scope_name)
    if branch_match:
        base_branch = branch_match.group(1) or os.environ.get("GIT_BASE_BRANCH", "main")
        return _run_git_command(["git", "diff", "--name-only", f"{base_branch}...HEAD"], base_path)

    git_commands = {
        "@git": ["git", "diff", "--name-only", "--cached"],
        "@git:staged": ["git", "diff", "--name-only", "--cached"],
        "@git:unstaged": ["git", "diff", "--name-only"],
        "@git:lastcommit": ["git", "show", "--pretty=format:", "--name-only", "HEAD"],
        "@git:conflicts": ["git", "diff", "--name-only", "--diff-filter=U"],
    }
    if scope_name in git_commands:
        return _run_git_command(git_commands[scope_name], base_path)

    if scope_name == "@recent":
        all_files = filter(Path.is_file, base_path.rglob('*'))
        excluded_dirs = ['.git', '__pycache__', 'node_modules', '.venv']
        filtered_files = [p for p in all_files if not any(excluded in p.parts for excluded in excluded_dirs)]
        return sorted(filtered_files, key=lambda p: p.stat().st_mtime, reverse=True)[:5]

    console.print(f"❌ Unknown or invalid dynamic scope '{scope_name}'.", style="red")
    return []