import re
import difflib
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.console import Group

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

def _generate_diff_lines(original_content: str, new_content: str, path: Path) -> list[Text]:
    """Generates a list of colorized rich Text objects for a diff."""
    diff_lines = []
    diff = difflib.unified_diff(
        original_content.splitlines(),
        new_content.splitlines(),
        fromfile=f"a/{path.name}",
        tofile=f"b/{path.name}",
        lineterm=""
    )
    
    for line in diff:
        if line.startswith('+'):
            diff_lines.append(Text(line, style="green"))
        elif line.startswith('-'):
            diff_lines.append(Text(line, style="red"))
        elif line.startswith('^'):
            diff_lines.append(Text(line, style="blue"))
        else:
            diff_lines.append(Text(line))
            
    return diff_lines

def paste_response(response_content: str):
    """
    Parses a response, writes changes to files, and displays a summary
    panel including a diff of all the changes.
    """
    files_written = []
    files_skipped = []
    files_failed = []
    summary_panels = []
    found_matches = False

    for target_path, code_content in _parse_file_blocks(response_content):
        found_matches = True
        original_content = None
        is_new_file = not target_path.exists()

        try:
            if not is_new_file:
                original_content = target_path.read_text('utf-8')
                if original_content == code_content:
                    files_skipped.append(str(target_path))
                    continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(code_content, 'utf-8')
            files_written.append(str(target_path))

            if is_new_file:
                title = f"[bold green]CREATED: {target_path}[/bold green]"
                border_style = "green"
                diff_lines = [Text(f"+ {line}", style="green") for line in code_content.splitlines()]
            else:
                title = f"[bold cyan]MODIFIED: {target_path}[/bold cyan]"
                border_style = "cyan"
                diff_lines = _generate_diff_lines(original_content, code_content, target_path)

            if diff_lines:
                summary_panels.append(Panel(Text("\n").join(diff_lines), title=title, border_style=border_style, expand=False))

        except Exception as e:
            files_failed.append(str(target_path))

    summary_text = Text()
    if not found_matches:
        summary_text.append("No file paths and code blocks matching the expected format were found.", style="yellow")
    else:
        if files_written:
            summary_text.append(f"✅ Successfully wrote {len(files_written)} file(s).\n", style="green")
        if files_skipped:
            summary_text.append(f"ℹ️  Skipped {len(files_skipped)} file(s) (no changes).\n", style="cyan")
        if files_failed:
            summary_text.append(f"❌ Failed to write {len(files_failed)} file(s).\n", style="red")
    
    # Prepend the summary text to the list of panels
    render_group = Group(*summary_panels, summary_text)
    console.print(Panel(render_group, title="[bold]Patch Summary[/bold]", border_style="blue"))

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
        if not path.exists():
            diff_panel = Panel(
                Text("\n").join(f"+ {line}" for line in new_content.splitlines()),
                title=f"[bold green]NEW FILE: {path}[/bold green]",
                border_style="green"
            )
            console.print(diff_panel)
            continue
            
        try:
            original_content = path.read_text('utf-8')
            diff_lines = _generate_diff_lines(original_content, new_content, path)
            diff_panel = Panel(
                Text("\n").join(diff_lines),
                title=f"[bold cyan]File: {path}[/bold cyan]",
                border_style="cyan"
            )
            console.print(diff_panel)
        except Exception as e:
            console.print(f"  [red]Could not generate diff: {e}[/red]")