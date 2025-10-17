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
        include_patterns = scope.get("include_patterns", [])
        exclude_patterns = scope.get("exclude_patterns", [])
        search = scope.get("search_words", [])
        urls = scope.get("urls", [])

        # Separate glob patterns from dynamic scopes
        glob_includes = [p for p in include_patterns if not p.startswith('@')]
        dynamic_includes = [p for p in include_patterns if p.startswith('@')]
        glob_excludes = [p for p in exclude_patterns if not p.startswith('@')]
        dynamic_excludes = [p for p in exclude_patterns if p.startswith('@')]

        included_files = set()
        excluded_files = set()

        # 1. Resolve glob includes
        if glob_includes:
            included_files.update(helpers.find_files(scope_path, glob_includes))

        # 2. Resolve dynamic includes
        for dyn_scope in dynamic_includes:
            included_files.update(resolvers.resolve_dynamic_scope(dyn_scope, base_path))

        # 3. Resolve glob excludes
        if glob_excludes:
            excluded_files.update(helpers.find_files(scope_path, glob_excludes))
        
        # 4. Resolve dynamic excludes
        for dyn_scope in dynamic_excludes:
            excluded_files.update(resolvers.resolve_dynamic_scope(dyn_scope, base_path))

        # 5. Combine and sort
        relevant_files = sorted(list(included_files - excluded_files))
        
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