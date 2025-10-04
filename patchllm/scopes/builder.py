from pathlib import Path
from rich.console import Console

from . import resolvers, structure, helpers
from .constants import DEFAULT_EXCLUDE_EXTENSIONS

console = Console()

def build_context_from_files(file_paths: list[Path], base_path: Path) -> dict | None:
    """Builds the context string directly from a provided list of file paths."""
    if not file_paths:
        console.print("\n⚠️  No files were provided to build the context.", style="yellow")
        return None
    return helpers._format_context(file_paths, [], base_path)

def build_context(scope_name: str, scopes: dict, base_path: Path) -> dict | None:
    """Builds the context string from files, handling static and dynamic scopes."""
    if scope_name == "@structure":
        return structure._build_structure_context(base_path)

    relevant_files = []
    urls = []

    if scope_name.startswith('@'):
        console.print(f"Resolving dynamic scope: [bold cyan]{scope_name}[/bold cyan]")
        relevant_files = resolvers.resolve_dynamic_scope(scope_name, base_path)
    else:
        scope = scopes.get(scope_name)
        if not scope:
            console.print(f"❌ Static scope '{scope_name}' not found.", style="red")
            return None
        
        scope_path = Path(scope.get("path", ".")).resolve()
        include = scope.get("include_patterns", [])
        exclude = scope.get("exclude_patterns", [])
        search = scope.get("search_words", [])
        urls = scope.get("urls", [])
        
        relevant_files = helpers.find_files(scope_path, include, exclude)
        if search:
            relevant_files = helpers.filter_files_by_keyword(relevant_files, search)

    if not relevant_files and not urls:
        console.print("\n⚠️  No files or URLs matched the specified criteria.", style="yellow")
        return None

    exclude_exts = scopes.get(scope_name, {}).get("exclude_extensions", DEFAULT_EXCLUDE_EXTENSIONS)
    norm_ext = {ext.lower() for ext in exclude_exts}
    relevant_files = [p for p in relevant_files if p.suffix.lower() not in norm_ext]

    if not relevant_files and not urls:
        console.print("\n⚠️  No files left after extension filtering.", style="yellow")
        return None

    return helpers._format_context(relevant_files, urls, base_path)