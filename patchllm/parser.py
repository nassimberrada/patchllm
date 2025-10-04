import re
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

def paste_response(response_content):
    """
    Parses a response containing code blocks and writes them to files.
    """
    pattern = re.compile(
        r"<file_path:([^>]+?)>\s*```(?:.*?)\n(.*?)\n```",
        re.DOTALL | re.MULTILINE
    )

    matches = pattern.finditer(response_content)
    
    files_written = []
    files_skipped = []
    files_failed = []
    found_matches = False

    for match in matches:
        found_matches = True
        file_path_str = match.group(1).strip()
        code_content = match.group(2)

        if not file_path_str:
            continue

        target_path = Path(file_path_str).resolve()

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)

            if target_path.exists() and target_path.read_text('utf-8') == code_content:
                files_skipped.append(target_path)
                continue

            target_path.write_text(code_content, 'utf-8')
            files_written.append(target_path)

        except Exception as e:
            files_failed.append(target_path)

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
        
    console.print(Panel(summary_text, title="[bold]Summary[/bold]", border_style="blue"))