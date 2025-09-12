import re
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

def paste_response(response_content):
    """
    Parses a response containing code blocks and writes them to files,
    handling both absolute and relative paths safely.

    Args:
        response_content (str): The string response from the LLM.
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
            console.print("⚠️ Found a code block with an empty file path. Skipping.", style="yellow")
            continue

        console.print(f"Found path in response: '[cyan]{file_path_str}[/]'")
        raw_path = Path(file_path_str)
        
        if raw_path.is_absolute():
            target_path = raw_path
        else:
            target_path = Path.cwd() / raw_path

        target_path = target_path.resolve()

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)

            if target_path.exists():
                with open(target_path, 'r', encoding='utf-8') as existing_file:
                    if existing_file.read() == code_content:
                        console.print(f"  -> No changes for '[cyan]{target_path}[/]', skipping.", style="dim")
                        files_skipped.append(target_path)
                        continue

            with open(target_path, 'w', encoding='utf-8') as outfile:
                outfile.write(code_content)

            console.print(f"  -> ✅ Wrote {len(code_content)} bytes to '[cyan]{target_path}[/]'", style="green")
            files_written.append(target_path)

        except OSError as e:
            console.print(f"  -> ❌ Error writing file '[cyan]{target_path}[/]': {e}", style="red")
            files_failed.append(target_path)
        except Exception as e:
            console.print(f"  -> ❌ An unexpected error occurred for file '[cyan]{target_path}[/]': {e}", style="red")
            files_failed.append(target_path)

    summary_text = Text()
    if not found_matches:
        summary_text.append("No file paths and code blocks matching the expected format were found in the response.", style="yellow")
    else:
        if files_written:
            summary_text.append(f"Successfully wrote {len(files_written)} file(s).\n", style="green")
        if files_skipped:
            summary_text.append(f"Skipped {len(files_skipped)} file(s) (no changes).\n", style="cyan")
        if files_failed:
            summary_text.append(f"Failed to write {len(files_failed)} file(s).\n", style="red")
        
        if not any([files_written, files_skipped, files_failed]):
             summary_text.append("Found matching blocks, but no files were processed.", style="yellow")

    console.print(Panel(summary_text, title="[bold]Summary[/bold]", border_style="blue"))