import re
from pathlib import Path
from rich.console import Console

from .constants import (
    STRUCTURE_EXCLUDE_DIRS, 
    DEFAULT_EXCLUDE_EXTENSIONS,
    LANGUAGE_PATTERNS,
    STRUCTURE_TEMPLATE
)

console = Console()

def _extract_symbols_by_regex(content: str, lang_patterns: list) -> dict:
    symbols = {"imports": [], "class": [], "function": []}
    for line in content.splitlines():
        for symbol_type, pattern in lang_patterns:
            match = pattern.match(line)
            if match:
                symbols[symbol_type].append(match.group(0).strip())
                break
    return symbols

def _build_structure_context(base_path: Path) -> dict | None:
    """Builds a context by extracting symbols from all project files."""
    all_files = []
    for p in base_path.rglob('*'):
        if any(part in STRUCTURE_EXCLUDE_DIRS for part in p.parts):
            continue
        if p.is_file() and p.suffix.lower() not in DEFAULT_EXCLUDE_EXTENSIONS:
            all_files.append(p)
    
    structure_outputs = []
    for file_path in sorted(all_files):
        lang = None
        for lang_name, config in LANGUAGE_PATTERNS.items():
            if file_path.suffix in config['extensions']:
                lang = lang_name
                break
        if lang:
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                symbols = _extract_symbols_by_regex(content, LANGUAGE_PATTERNS[lang]['patterns'])
                if any(symbols.values()):
                    rel_path = file_path.relative_to(base_path)
                    output = [f"<file_path:{rel_path.as_posix()}>"]
                    if symbols['imports']:
                        output.append("[imports]")
                        output.extend([f"- {s}" for s in symbols['imports']])
                    if symbols['class'] or symbols['function']:
                         output.append("[symbols]")
                         output.extend([f"- {s}" for s in symbols['class']])
                         output.extend([f"- {s}" for s in symbols['function']])
                    structure_outputs.append("\n".join(output))
            except Exception as e:
                console.print(f"⚠️ Could not process {file_path}: {e}", style="yellow")

    if not structure_outputs: return None
    final_content = "\n\n".join(structure_outputs)
    final_context = STRUCTURE_TEMPLATE.replace("{{structure_content}}", final_content)
    return {"tree": "Project structure view", "context": final_context}