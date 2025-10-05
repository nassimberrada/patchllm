import pytest
from prompt_toolkit.document import Document

# This import will only work if prompt_toolkit is installed
pytest.importorskip("prompt_toolkit")

from patchllm.tui.completer import PatchLLMCompleter

@pytest.fixture
def completer():
    """Provides a PatchLLMCompleter instance with mock data."""
    mock_commands = ["/task", "/plan", "/context", "/clear_context"]
    mock_scopes = {"base": {}, "js_files": {}}
    return PatchLLMCompleter(mock_commands, mock_scopes)

def test_command_completion(completer):
    """Tests that commands starting with '/' are completed correctly."""
    doc = Document("/c")
    completions = list(completer.get_completions(doc, None))
    completion_texts = {c.text for c in completions}
    
    assert "/context" in completion_texts
    assert "/clear_context" in completion_texts
    assert "/task" not in completion_texts

def test_scope_completion(completer):
    """Tests that scopes are completed after a context command."""
    doc = Document("/context @git:s")
    completions = list(completer.get_completions(doc, None))
    completion_texts = {c.text for c in completions}

    assert "@git:staged" in completion_texts
    assert "@git:staged" in completion_texts
    assert "base" not in completion_texts

def test_scope_completion_after_space(completer):
    """Tests that all scopes are suggested after a space."""
    doc = Document("/add_context ")
    completions = list(completer.get_completions(doc, None))
    # Should suggest all scopes
    assert len(completions) == len(completer.all_scopes)

def test_no_completion_for_irrelevant_text(completer):
    """Tests that no completions are offered for arbitrary text."""
    doc = Document("hello world")
    completions = list(completer.get_completions(doc, None))
    assert len(completions) == 0