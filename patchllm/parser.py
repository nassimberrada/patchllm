import difflib
import re
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

def _parse_file_blocks(response: str) -> list[tuple[Path, str]]:
    """Parses the LLM response to extract file paths and their content."""
    pattern = r"<file_path:(.*?)>\n```(?:\w+\n)?(.*?)\n```"
    matches = re.findall(pattern, response, re.DOTALL)
    
    parsed_blocks = []
    for path_str, content in matches:
        path_obj = Path(path_str.strip()).resolve()
        # --- CORRECTION: Strip leading/trailing whitespace from content ---
        parsed_blocks.append((path_obj, content.strip()))
        
    return parsed_blocks

def parse_change_summary(response: str) -> str | None:
    """Parses the LLM response to extract the change summary."""
    pattern = r"<change_summary>(.*?)</change_summary>"
    match = re.search(pattern, response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None

def paste_response(response: str):
    """Applies all file updates from the LLM's response to the local filesystem."""
    parsed_blocks = _parse_file_blocks(response)
    if not parsed_blocks:
        console.print("⚠️  Could not find any file blocks to apply in the response.", style="yellow")
        return
        
    for file_path, new_content in parsed_blocks:
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(new_content, encoding="utf-8")
            console.print(f"✅ Updated [bold cyan]{file_path.name}[/bold cyan]", style="green")
        except Exception as e:
            console.print(f"❌ Failed to write to {file_path}: {e}", style="red")

def paste_response_selectively(response: str, files_to_apply: list[str]):
    """
    Applies file updates from the LLM's response only to the user-selected files.

    Args:
        response (str): The full response from the LLM.
        files_to_apply (list[str]): A list of absolute file path strings to modify.
    """
    parsed_blocks = _parse_file_blocks(response)
    if not parsed_blocks:
        console.print("⚠️  Could not find any file blocks to apply in the response.", style="yellow")
        return

    files_to_apply_set = set(files_to_apply)
    applied_count = 0

    for file_path, new_content in parsed_blocks:
        if file_path.as_posix() in files_to_apply_set:
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(new_content, encoding="utf-8")
                console.print(f"✅ Updated [bold cyan]{file_path.name}[/bold cyan]", style="green")
                applied_count += 1
            except Exception as e:
                console.print(f"❌ Failed to write to {file_path}: {e}", style="red")

    if applied_count == 0:
        console.print("No changes were applied.", style="yellow")


def summarize_changes(response: str) -> dict:
    """Summarizes which files will be created and which will be modified."""
    parsed_blocks = _parse_file_blocks(response)
    summary = {"created": [], "modified": []}
    for file_path, _ in parsed_blocks:
        if file_path.exists():
            summary["modified"].append(file_path.as_posix())
        else:
            summary["created"].append(file_path.as_posix())
    return summary

def get_diff_for_file(file_path_str: str, response: str) -> str:
    """Generates a colorized, unified diff for a single file from the response."""
    parsed_blocks = _parse_file_blocks(response)
    file_path = Path(file_path_str).resolve()
    
    new_content = None
    for p, content in parsed_blocks:
        if p == file_path:
            new_content = content
            break
            
    if new_content is None:
        return f"Could not find content for {file_path_str} in the response."

    original_content = ""
    if file_path.exists():
        try:
            original_content = file_path.read_text(encoding="utf-8")
        except Exception:
            return f"Could not read original content of {file_path_str}."

    diff = difflib.unified_diff(
        original_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"a/{file_path.name}",
        tofile=f"b/{file_path.name}",
    )

    diff_text = Text()
    for line in diff:
        if line.startswith('+'):
            diff_text.append(line, style="green")
        elif line.startswith('-'):
            diff_text.append(line, style="red")
        elif line.startswith('^'):
            diff_text.append(line, style="blue")
        else:
            diff_text.append(line)
            
    return diff_text

def display_diff(response: str):
    """Displays the diff for all changes proposed in the response."""
    summary = summarize_changes(response)
    all_files = summary.get("modified", []) + summary.get("created", [])
    
    console.print("\n--- Proposed Changes (Diff) ---", style="bold yellow")
    
    if not all_files:
        console.print("No file changes detected in the response.")
        return
        
    for file_path in all_files:
        diff_text = get_diff_for_file(file_path, response)
        console.print(Panel(diff_text, title=f"[bold cyan]Diff: {Path(file_path).name}[/bold cyan]", border_style="yellow"))