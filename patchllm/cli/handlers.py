import pprint
import ast
import textwrap
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from ..utils import write_scopes_to_file
from ..parser import paste_response
from ..scopes.builder import build_context, build_context_from_files
from ..llm import run_llm_query

console = Console()

def handle_init(scopes_file_path):
    if Path(scopes_file_path).exists():
        console.print(f"⚠️  '{scopes_file_path}' already exists. Aborting.", style="yellow")
        return
    default_scopes = {"base": {"path": ".", "include_patterns": ["**/*"], "exclude_patterns": []}}
    write_scopes_to_file(scopes_file_path, default_scopes)
    console.print(f"✅ Successfully created '{scopes_file_path}'.", style="green")

def handle_scope_management(args, scopes, scopes_file_path, parser):
    """Handles all commands related to managing scopes."""
    if args.list_scopes:
        console.print(f"Available scopes in '[bold]{scopes_file_path}[/]':", style="bold")
        if not scopes:
            console.print(f"  -> No scopes found.")
        else:
            for scope_name in sorted(scopes.keys()):
                console.print(f"  - {scope_name}")

    elif args.show_scope:
        scope_data = scopes.get(args.show_scope)
        if scope_data:
            console.print(Panel(pprint.pformat(scope_data, indent=2), title=f"[bold cyan]Scope: '{args.show_scope}'[/]"))
        else:
            console.print(f"❌ Scope '[bold]{args.show_scope}[/]' not found.", style="red")

    elif args.add_scope:
        if args.add_scope in scopes:
            console.print(f"❌ Scope '[bold]{args.add_scope}[/]' already exists.", style="red")
            return
        scopes[args.add_scope] = {"path": ".", "include_patterns": ["**/*"], "exclude_patterns": []}
        write_scopes_to_file(scopes_file_path, scopes)

    elif args.remove_scope:
        if args.remove_scope not in scopes:
            console.print(f"❌ Scope '[bold]{args.remove_scope}[/]' not found.", style="red")
            return
        del scopes[args.remove_scope]
        write_scopes_to_file(scopes_file_path, scopes)

    elif args.update_scope:
        if len(args.update_scope) < 2:
            parser.error("--update-scope requires a scope name and at least one 'key=value' pair.")
        scope_name = args.update_scope[0]
        updates = args.update_scope[1:]
        if scope_name not in scopes:
            console.print(f"❌ Scope '[bold]{scope_name}[/]' not found.", style="red")
            return
        try:
            for update in updates:
                key, value_str = update.split('=', 1)
                value = ast.literal_eval(value_str)
                scopes[scope_name][key.strip()] = value
            write_scopes_to_file(scopes_file_path, scopes)
        except (ValueError, SyntaxError) as e:
            console.print(f"❌ Error parsing update values: {e}", style="red")

def handle_file_io(args):
    """Handles commands that read from files or clipboard to apply patches."""
    if args.from_clipboard:
        try:
            import pyperclip
            updates = pyperclip.paste()
            if updates:
                paste_response(updates)
            else:
                console.print("⚠️ Clipboard is empty.", style="yellow")
        except ImportError:
            console.print("❌ 'pyperclip' is required. `pip install pyperclip`", style="red")
    elif args.from_file:
        try:
            updates = Path(args.from_file).read_text(encoding="utf-8")
            paste_response(updates)
        except Exception as e:
            console.print(f"❌ Failed to read from file {args.from_file}: {e}", style="red")

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
        tree, context = context_object.values()
        console.print("\n--- Context Summary ---", style="bold")
        console.print(tree)
        return context
    
    if any([args.interactive, args.scope]):
        console.print("--- Context building failed or returned no files. ---", style="yellow")
    return None

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

def handle_main_task_flow(args, scopes, recipes, parser):
    """Handles the primary workflow of building context and querying the LLM."""
    system_prompt = get_system_prompt()
    history = [{"role": "system", "content": system_prompt}]
    
    task = args.task
    if args.recipe:
        if args.task:
            console.print(f"⚠️ Both --task and --recipe provided. Using explicit --task.", style="yellow")
        else:
            task = recipes.get(args.recipe)
            if not task:
                parser.error(f"Recipe '{args.recipe}' not found in recipes file.")

    context = None
    if args.context_in:
        context = Path(args.context_in).read_text()
    else:
        context = _collect_context(args, scopes)
        if context is None and not args.guidelines:
             if any([args.scope, args.interactive]):
                 return # Exit if context building failed
             if task:
                 parser.error("A scope (-s), interactive (-in), or context-in (-ci) is required for a task or recipe.")

    if args.guidelines:
        guidelines_content = system_prompt if args.guidelines is True else args.guidelines
        context = f"{guidelines_content}\n\n{context}" if context else guidelines_content

    if args.context_out and context:
        Path(args.context_out).write_text(context)

    if task:
        action_flags = [args.patch, args.to_file is not None, args.to_clipboard]
        if sum(action_flags) > 1:
            parser.error("Please specify only one action: --patch, --to-file, or --to-clipboard.")
        if sum(action_flags) == 0:
            parser.error("A task or recipe was provided, but no action was specified (e.g., --patch).")

        if not context:
            console.print("Proceeding with task but without any file context.", style="yellow")

        llm_response = run_llm_query(task, args.model, history, context)
        
        if llm_response:
            if args.patch:
                paste_response(llm_response)
            elif args.to_file is not None:
                Path(args.to_file).write_text(llm_response)
            elif args.to_clipboard:
                try:
                    import pyperclip
                    pyperclip.copy(llm_response)
                    console.print("✅ Copied to clipboard.", style="green")
                except ImportError:
                    console.print("❌ 'pyperclip' is required. `pip install pyperclip`", style="red")

def handle_voice_flow(args, scopes, parser):
    """Handles the voice-activated workflow."""
    try:
        from ..voice.listener import listen, speak
    except ImportError:
        console.print("❌ Voice dependencies are not installed.", style="red")
        console.print("   Install with: pip install 'patchllm[voice]'", style="cyan")
        return

    speak("Say your task instruction.")
    task = listen()
    if not task:
        speak("No instruction heard. Exiting.")
        return
    
    speak(f"You said: {task}. Should I proceed?")
    confirm = listen()
    if confirm and "yes" in confirm.lower():
        context = _collect_context(args, scopes)
        if context is None:
            speak("Context building failed. Exiting.")
            return

        system_prompt = get_system_prompt()
        history = [{"role": "system", "content": system_prompt}]
        
        llm_response = run_llm_query(task, args.model, history, context)
        if llm_response:
            paste_response(llm_response)
            speak("Changes applied.")
    else:
        speak("Cancelled.")

def handle_chat_flow(args, scopes, recipes):
    """Handles the interactive chat workflow."""
    try:
        from ..chat.chat import ChatSession
        session = ChatSession(args, scopes, recipes)
        session.start()
    except ImportError:
        console.print("❌ 'InquirerPy' is required for chat mode.", style="red")
        console.print("   Install it with: pip install 'patchllm[interactive]'", style="cyan")
    except KeyboardInterrupt:
        console.print("\n👋 Chat session ended by user.", style="bold yellow")
    except Exception as e:
        console.print(f"❌ An unexpected error occurred in chat mode: {e}", style="red")