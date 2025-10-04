import re
import difflib
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

def _parse_file_blocks(response_content):
    """Generator that yields file path and content from a response."""
    pattern = re.compile(
        r"<file_path:([^>]+?)>\s*```(?:.*?)\n(.*?)\n```",
        re.DOTALL | re.MULTILINE
    )
    for match in pattern.finditer(response_content):
        file_path_str = match.group(1).strip()
        code_content = match.group(2)
        if file_path_str:
            yield Path(file_path_str).resolve(), code_content

def paste_response(response_content):
    """
    Parses a response containing code blocks and writes them to files.
    """
    files_written = []
    files_skipped = []
    files_failed = []
    found_matches = False

    for target_path, code_content in _parse_file_blocks(response_content):
        found_matches = True
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)

            if target_path.exists() and target_path.read_text('utf-8') == code_content:
                files_skipped.append(str(target_path))
                continue

            target_path.write_text(code_content, 'utf-8')
            files_written.append(str(target_path))

        except Exception as e:
            files_failed.append(str(target_path))

    summary_text = Text()
    if not found_matches:
        summary_text.append("No file paths and code blocks matching the expected format were found.", style="yellow")
    else:
        if files_written:
            summary_text.append(f"Successfully wrote {len(files_written)} file(s).\n", style="green")
        if files_skipped:
            summary_text.append(f"Skipped {len(files_skipped)} file(s) (no changes).\n", style="cyan")
        if files_failed:
            summary_text.append(f"Failed to write {len(files_failed)} file(s).\n", style="red")
        
    console.print(Panel(summary_text, title="[bold]Patch Summary[/bold]", border_style="blue"))

def summarize_changes(response_content):
    """Parses the response and returns a summary of changes."""
    created_files = []
    modified_files = []

    for path, _ in _parse_file_blocks(response_content):
        if path.exists():
            modified_files.append(str(path))
        else:
            created_files.append(str(path))
            
    return {"created": created_files, "modified": modified_files}

def display_diff(response_content):
    """Displays a unified diff for the proposed changes."""
    console.print("\n--- Proposed Changes (Diff) ---", style="bold yellow")
    
    for path, new_content in _parse_file_blocks(response_content):
        console.print(Panel(f"[bold cyan]File: {path}[/bold cyan]", border_style="cyan"))
        
        if not path.exists():
            console.print(Text(f"+ {line}", style="green") for line in new_content.splitlines())
            console.print()
            continue
            
        try:
            original_content = path.read_text('utf-8')
            diff = difflib.unified_diff(
                original_content.splitlines(),
                new_content.splitlines(),
                fromfile=f"a/{path.name}",
                tofile=f"b/{path.name}",
                lineterm=""
            )
            
            for line in diff:
                if line.startswith('+'):
                    console.print(Text(line, style="green"))
                elif line.startswith('-'):
                    console.print(Text(line, style="red"))
                elif line.startswith('^'):
                    console.print(Text(line, style="blue"))
                else:
                    console.print(line)
            console.print() # Add a blank line for spacing
        except Exception as e:
            console.print(f"  [red]Could not generate diff: {e}[/red]")