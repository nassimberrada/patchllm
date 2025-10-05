import pytest
from unittest.mock import patch, MagicMock
import sys
import os
from pathlib import Path

from patchllm.cli.entrypoint import main
from patchllm.agent.session import AgentSession

@pytest.fixture
def mock_args():
    """Provides a mock argparse.Namespace object for tests."""
    return MagicMock()

def test_agent_session_initialization(mock_args):
    """
    Tests that the AgentSession is created with the correct default states.
    """
    # --- FIX: Pass the required mock_args parameter to the constructor ---
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    assert session.goal is None
    assert session.plan == []
    assert session.current_step == 0
    assert session.context is None
    assert session.context_files == []
    assert len(session.history) == 1
    assert session.history[0]["role"] == "system"
    assert "You are an expert pair programmer" in session.history[0]["content"]

@patch('rich.console.Console.input')
def test_tui_launches_and_exits(mock_input, temp_project, capsys):
    """
    Tests that running `patchllm` with no args launches the TUI and that
    the `/exit` command terminates it gracefully.
    """
    os.chdir(temp_project)
    mock_input.return_value = "/exit"
    with patch.object(sys, 'argv', ['patchllm']):
        main()
    captured = capsys.readouterr()
    assert "Welcome to the PatchLLM Agent" in captured.out
    assert "Exiting agent session. Goodbye!" in captured.out
    mock_input.assert_called_once()

@patch('rich.console.Console.input')
def test_tui_help_command(mock_input, temp_project, capsys):
    """
    Tests that the /help command displays the help message.
    """
    os.chdir(temp_project)
    mock_input.side_effect = ["/help", "/exit"]
    with patch.object(sys, 'argv', ['patchllm']):
        main()
    captured = capsys.readouterr()
    assert "PatchLLM Agent Commands" in captured.out
    assert "/context <scope>" in captured.out

@patch('patchllm.tui.interface.AgentSession')
@patch('rich.console.Console.input')
def test_tui_context_command_calls_session(mock_input, mock_agent_session, temp_project):
    """
    Tests that typing `/context <scope>` in the TUI calls the correct
    method on the AgentSession instance.
    """
    os.chdir(temp_project)
    
    mock_session_instance = mock_agent_session.return_value
    mock_session_instance.load_context_from_scope.return_value = "Mocked context summary"
    
    mock_input.side_effect = ["/context my_scope", "/exit"]

    with patch.object(sys, 'argv', ['patchllm']):
        main()

    mock_session_instance.load_context_from_scope.assert_called_once_with("my_scope")

@patch('patchllm.tui.interface.select_files_interactively')
@patch('patchllm.tui.interface.AgentSession')
@patch('rich.console.Console.input')
def test_tui_interactive_add_context_command(mock_input, mock_agent_session, mock_selector, temp_project):
    """
    Tests the flow for the `/add_context --interactive` command.
    """
    os.chdir(temp_project)
    
    mock_session_instance = mock_agent_session.return_value
    mock_file_path = Path(temp_project / "selected.py").resolve()
    mock_selector.return_value = [mock_file_path]
    
    mock_input.side_effect = ["/add_context --interactive", "/exit"]
    
    with patch.object(sys, 'argv', ['patchllm']):
        main()
        
    mock_selector.assert_called_once()
    
    mock_session_instance.add_files_and_rebuild_context.assert_called_once_with([mock_file_path])