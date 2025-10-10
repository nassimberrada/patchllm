import textwrap
from pathlib import Path
from rich.console import Console

from ..scopes.builder import build_context, build_context_from_files

console = Console()

def get_system_prompt():
    """Returns the system prompt for the LLM."""
    return textwrap.dedent("""
        You are an expert pair programmer. Your purpose is to help users by modifying files based on their instructions.
        Follow these rules strictly:
        Your output should be a single file including all the updated files. For each file-block:
        1. Only include code for files that need to be updated / edited.
        2. For updated files, do not exclude any code even if it is unchanged code; assume the file code will be copy-pasted full in the file.
        3. Do not include verbose inline comments explaining what every small change does. Try to keep comments concise but informative, if any.
        4. Only update the relevant parts of each file relative to the provided task; do not make irrelevant edits even if you notice areas of improvements elsewhere.
        5. Do not use diffs.
        6. Make sure each file-block is returned in the following exact format. No additional text, comments, or explanations should be outside these blocks.
        Expected format for a modified or new file:
        <file_path:/absolute/path/to/your/file.py>
        ```python
        # The full, complete content of /absolute/path/to/your/file.py goes here.
        def example_function():
            return "Hello, World!"
        ```
    """)

def _collect_context(args, scopes):
    """Helper to determine and build the context from args."""
    base_path = Path(".").resolve()
    context_object = None

    if args.interactive:
        try:
            from ..interactive.selector import select_files_interactively
            selected_files = select_files_interactively(base_path)
            if selected_files:
                context_object = build_context_from_files(selected_files, base_path)
        except ImportError:
            console.print("❌ 'InquirerPy' is required for interactive mode.", style="red")
            console.print("   Install it with: pip install 'patchllm[interactive]'", style="cyan")
            return None
    elif args.scope:
        context_object = build_context(args.scope, scopes, base_path)

    if context_object:
        tree = context_object.get("tree", "")
        console.print("\n--- Context Summary ---", style="bold")
        console.print(tree)
        
        return context_object
    
    if any([args.interactive, args.scope]):
        console.print("--- Context building failed or returned no files. ---", style="yellow")
    return None