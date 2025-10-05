import pytest
from unittest.mock import patch, MagicMock
import sys
import os
from pathlib import Path

# This import will only work if prompt_toolkit is installed
pytest.importorskip("prompt_toolkit")

from patchllm.cli.entrypoint import main
from patchllm.agent.session import AgentSession

@pytest.fixture
def mock_args():
    """Provides a mock argparse.Namespace object for tests."""
    return MagicMock()

def test_agent_session_initialization(mock_args):
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    assert session.goal is None
    assert session.plan == []

# --- MODIFICATION: Changed patch target for all TUI tests ---

@patch('prompt_toolkit.PromptSession.prompt')
def test_tui_launches_and_exits(mock_prompt, temp_project, capsys):
    os.chdir(temp_project)
    mock_prompt.return_value = "/exit"
    with patch.object(sys, 'argv', ['patchllm']):
        main()
    captured = capsys.readouterr()
    assert "Welcome to the PatchLLM Agent" in captured.out
    assert "Exiting agent session. Goodbye!" in captured.out
    mock_prompt.assert_called_once()

@patch('prompt_toolkit.PromptSession.prompt')
def test_tui_help_command(mock_prompt, temp_project, capsys):
    os.chdir(temp_project)
    mock_prompt.side_effect = ["/help", "/exit"]
    with patch.object(sys, 'argv', ['patchllm']):
        main()
    captured = capsys.readouterr()
    assert "PatchLLM Agent Commands" in captured.out
    assert "/context <scope>" in captured.out

@patch('patchllm.tui.interface.AgentSession')
@patch('prompt_toolkit.PromptSession.prompt')
def test_tui_context_command_calls_session(mock_prompt, mock_agent_session, temp_project):
    os.chdir(temp_project)
    mock_session_instance = mock_agent_session.return_value
    mock_session_instance.load_context_from_scope.return_value = "Mocked context summary"
    mock_prompt.side_effect = ["/context my_scope", "/exit"]
    with patch.object(sys, 'argv', ['patchllm']):
        main()
    mock_session_instance.load_context_from_scope.assert_called_once_with("my_scope")

@patch('patchllm.tui.interface.select_files_interactively')
@patch('patchllm.tui.interface.AgentSession')
@patch('prompt_toolkit.PromptSession.prompt')
def test_tui_interactive_add_context_command(mock_prompt, mock_agent_session, mock_selector, temp_project):
    os.chdir(temp_project)
    mock_session_instance = mock_agent_session.return_value
    mock_file_path = Path(temp_project / "selected.py").resolve()
    mock_selector.return_value = [mock_file_path]
    mock_prompt.side_effect = ["/add_context --interactive", "/exit"]
    with patch.object(sys, 'argv', ['patchllm']):
        main()
    mock_selector.assert_called_once()
    mock_session_instance.add_files_and_rebuild_context.assert_called_once_with([mock_file_path])