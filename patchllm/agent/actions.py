import subprocess
from rich.console import Console
from rich.panel import Panel

console = Console()

def run_tests():
    """
    Runs tests using pytest and displays the output.
    """
    console.print("\n--- Running Tests ---", style="bold yellow")
    try:
        process = subprocess.run(
            ["pytest"],
            capture_output=True,
            text=True,
            check=False  # We don't want to crash if tests fail
        )
        
        output = process.stdout + process.stderr
        
        if process.returncode == 0:
            title = "[bold green]✅ Tests Passed[/bold green]"
            border_style = "green"
        else:
            title = "[bold red]❌ Tests Failed[/bold red]"
            border_style = "red"
            
        console.print(Panel(output, title=title, border_style=border_style, expand=True))

    except FileNotFoundError:
        console.print("❌ 'pytest' command not found. Is it installed and in your PATH?", style="red")
    except Exception as e:
        console.print(f"❌ An unexpected error occurred while running tests: {e}", style="red")


def stage_files(files_to_stage: list[str] = None):
    """
    Stages files using git. If no files are specified, stages all changes.

    Args:
        files_to_stage (list[str], optional): A list of specific files to stage. Defaults to None.
    """
    command = ["git", "add"]
    action_desc = "all changes"
    if files_to_stage:
        command.extend(files_to_stage)
        action_desc = f"{len(files_to_stage)} file(s)"
    else:
        command.append(".")

    console.print(f"\n--- Staging {action_desc} ---", style="bold yellow")
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True
        )
        
        output = process.stdout + process.stderr
        if output:
            console.print(output, style="dim")
            
        console.print("✅ Files staged successfully.", style="green")

    except FileNotFoundError:
        console.print("❌ 'git' command not found. Is it installed and in your PATH?", style="red")
    except subprocess.CalledProcessError as e:
        console.print("❌ Failed to stage files.", style="red")
        console.print(e.stderr)
    except Exception as e:
        console.print(f"❌ An unexpected error occurred while staging files: {e}", style="red")