import pprint
import ast
import textwrap
import re
import argparse
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from ..utils import write_scopes_to_file
from ..parser import paste_response
from ..patcher import apply_external_patch
from ..scopes.builder import build_context_from_files, helpers
from ..llm import run_llm_query
from .helpers import get_system_prompt, _collect_context

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
        console.print(f"✅ Scope '[bold]{args.add_scope}[/]' added.", style="green")


    elif args.remove_scope:
        if args.remove_scope not in scopes:
            console.print(f"❌ Scope '[bold]{args.remove_scope}[/]' not found.", style="red")
            return
        del scopes[args.remove_scope]
        write_scopes_to_file(scopes_file_path, scopes)
        console.print(f"✅ Scope '[bold]{args.remove_scope}[/]' removed.", style="green")

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
    content_to_patch = None
    if args.from_clipboard:
        try:
            import pyperclip
            content_to_patch = pyperclip.paste()
            if not content_to_patch:
                console.print("⚠️ Clipboard is empty.", style="yellow")
                return
        except ImportError:
            console.print("❌ 'pyperclip' is required. `pip install pyperclip`", style="red")
            return
    elif args.from_file:
        try:
            content_to_patch = Path(args.from_file).read_text(encoding="utf-8")
        except Exception as e:
            console.print(f"❌ Failed to read from file {args.from_file}: {e}", style="red")
            return

    if content_to_patch:
        base_path = Path(".").resolve()
        apply_external_patch(content_to_patch, base_path)

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
        context_object = _collect_context(args, scopes)
        context = context_object.get("context") if context_object else None
        if context is None and not args.guidelines:
             if any([args.scope, args.interactive]):
                 return
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
        context_object = _collect_context(args, scopes)
        context = context_object.get("context") if context_object else None
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