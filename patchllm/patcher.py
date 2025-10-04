import subprocess
import re
from pathlib import Path
from rich.console import Console
from InquirerPy import prompt
from InquirerPy.exceptions import InvalidArgument
import textwrap

from .parser import get_diff_for_file, _parse_file_blocks, paste_response
from .scopes.helpers import find_files

console = Console()

def _is_diff_format(text: str) -> bool:
    """Checks if the text appears to be in the unified diff format."""
    for line in text.splitlines():
        if line.strip(): # Find the first non-empty line
            return line.startswith("--- a/")
    return False

def _apply_diff(diff_text: str, base_path: Path):
    """Applies a patch using the system's `patch` command."""
    try:
        # --- MODIFICATION: Added --ignore-whitespace for robustness ---
        proc = subprocess.run(
            ["patch", "-p1", "--ignore-whitespace"],
            input=diff_text,
            text=True,
            capture_output=True,
            check=True,
            cwd=base_path
        )
        console.print("✅ Patch applied successfully.", style="green")
        if proc.stdout:
            console.print(proc.stdout)
    except FileNotFoundError:
        console.print("❌ Failed to apply patch.", style="red")
        console.print("Error: The 'patch' command-line utility was not found.", style="yellow")
        console.print("Please install it to apply diff-formatted patches:", style="yellow")
        console.print("  - On Debian/Ubuntu: sudo apt-get install patch", style="cyan")
        console.print("  - On macOS (Homebrew): brew install patch", style="cyan")
        console.print("  - On Termux: pkg install patch", style="cyan")
    except subprocess.CalledProcessError as e:
        console.print("❌ Failed to apply patch.", style="red")
        console.print("The `patch` command failed. This may be due to a mismatch between the diff and the file content.", style="yellow")
        if e.stderr:
            console.print("Error details:", style="yellow")
            console.print(e.stderr)
    except Exception as e:
        console.print(f"❌ An unexpected error occurred while applying the patch: {e}", style="red")


def _interactive_file_selection(base_path: Path) -> Path | None:
    """Prompts the user to select a file from the project."""
    try:
        all_files = find_files(base_path, ["**/*"])
        choices = [p.relative_to(base_path).as_posix() for p in all_files]
        if not choices:
            console.print("No files found in the project.", style="yellow")
            return None

        question = {
            "type": "fuzzy", "name": "file", "message": "Which file should this code be applied to?",
            "choices": choices, "border": True
        }
        result = prompt([question], vi_mode=True)
        return base_path / result.get("file") if result else None
    except (InvalidArgument, IndexError, KeyError):
        return None

def apply_external_patch(content: str, base_path: Path):
    """
    Intelligently applies code updates from an external source.
    Handles standard diffs, patchllm's format, and ambiguous code blocks.
    """
    if _is_diff_format(content):
        console.print("Detected `diff` format. Attempting to apply with `patch`...", style="cyan")
        _apply_diff(content, base_path)
        return

    clean_content = textwrap.dedent(content).strip()

    parsed_blocks = _parse_file_blocks(clean_content)
    if parsed_blocks:
        console.print("Detected `patchllm` format. Applying changes...", style="cyan")
        paste_response(clean_content)
        return

    console.print("Could not parse a standard format. Entering interactive mode...", style="yellow")
    
    code_block_match = re.search(r"```(?:\w+)?\s*\n(.*?)\n\s*```", clean_content, re.DOTALL)
    if not code_block_match:
        console.print("❌ No code blocks found in the input.", style="red")
        return
        
    code_to_apply = code_block_match.group(1).strip()
    target_file = _interactive_file_selection(base_path)

    if not target_file:
        console.print("Cancelled.", style="yellow")
        return

    response_for_diff = f"<file_path:{target_file.as_posix()}>\n```\n{code_to_apply}\n```"
    diff_text = get_diff_for_file(str(target_file), response_for_diff)
    console.print("\n--- Proposed Changes ---", style="bold yellow")
    console.print(diff_text)
    
    try:
        confirm_q = {"type": "confirm", "name": "confirm", "message": f"Apply these changes to '{target_file.name}'?", "default": True}
        result = prompt([confirm_q])
        if result and result.get("confirm"):
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(code_to_apply, encoding="utf-8")
            console.print(f"✅ Updated [bold cyan]{target_file.name}[/bold cyan]", style="green")
        else:
            console.print("Cancelled.", style="yellow")
    except (InvalidArgument, IndexError, KeyError):
        console.print("Cancelled.", style="yellow")