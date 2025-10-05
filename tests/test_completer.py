import pytest
from prompt_toolkit.document import Document
from prompt_toolkit.completion import Completion
# --- FIX: Import the necessary helper function ---
from prompt_toolkit.formatted_text import to_plain_text

# This import will only work if prompt_toolkit is installed
pytest.importorskip("prompt_toolkit")

from patchllm.tui.completer import PatchLLMCompleter, COMMAND_META

@pytest.fixture
def completer():
    """Provides a PatchLLMCompleter instance with mock data."""
    mock_commands = list(COMMAND_META.keys())
    mock_scopes = {"base": {}, "js_files": {}}
    return PatchLLMCompleter(mock_commands, mock_scopes)

def test_command_completion_with_meta(completer):
    """Tests that commands are completed with the correct descriptive metadata."""
    doc = Document("/c")
    completions = list(completer.get_completions(doc, None))
    
    # Find the completion for /context
    context_completion = next((c for c in completions if c.text == '/context'), None)
    assert context_completion is not None
    # --- FIX: Use to_plain_text for correct string conversion ---
    assert to_plain_text(context_completion.display_meta) == COMMAND_META['/context']

    # Find the completion for /clear_context
    clear_completion = next((c for c in completions if c.text == '/clear_context'), None)
    assert clear_completion is not None
    # --- FIX: Use to_plain_text for correct string conversion ---
    assert to_plain_text(clear_completion.display_meta) == COMMAND_META['/clear_context']

def test_scope_completion_with_meta(completer):
    """Tests that scopes are completed with metadata distinguishing static vs dynamic."""
    doc = Document("/context @git:s")
    completions = list(completer.get_completions(doc, None))
    
    staged_completion = next((c for c in completions if c.text == '@git:staged'), None)
    assert staged_completion is not None
    # --- FIX: Use to_plain_text for correct string conversion ---
    assert to_plain_text(staged_completion.display_meta) == "Dynamic scope"

    doc_base = Document("/context ba")
    completions_base = list(completer.get_completions(doc_base, None))
    base_completion = next((c for c in completions_base if c.text == 'base'), None)
    assert base_completion is not None
    # --- FIX: Use to_plain_text for correct string conversion ---
    assert to_plain_text(base_completion.display_meta) == "Static scope"


def test_scope_completion_after_space(completer):
    """Tests that all scopes are suggested after a space."""
    doc = Document("/add_context ")
    completions = list(completer.get_completions(doc, None))
    # Should suggest all scopes
    assert len(completions) == len(completer.all_scopes)

def test_plan_sub_command_completion_after_space(completer):
    """Tests that plan sub-commands are suggested after '/plan '."""
    doc = Document("/plan ")
    completions = list(completer.get_completions(doc, None))
    completion_texts = {c.text for c in completions}
    assert "--edit " in completion_texts
    assert "--rm " in completion_texts
    assert "--add " in completion_texts

def test_plan_sub_command_completion_typing(completer):
    """Tests partial completion of a plan sub-command."""
    doc = Document("/plan --e")
    completions = list(completer.get_completions(doc, None))
    completion_texts = {c.text for c in completions}
    assert "--edit " in completion_texts
    assert len(completions) == 1

def test_no_completion_for_irrelevant_text(completer):
    """Tests that no completions are offered for arbitrary text."""
    doc = Document("hello world")
    completions = list(completer.get_completions(doc, None))
    assert len(completions) == 0