import pytest
from unittest.mock import patch, MagicMock
import sys
import os
from pathlib import Path

# This import will only work if prompt_toolkit is installed
pytest.importorskip("prompt_toolkit")
# Add skip for the new dependency to avoid errors if not installed
pytest.importorskip("InquirerPy")

from patchllm.cli.entrypoint import main
from patchllm.agent.session import AgentSession

@pytest.fixture
def mock_args():
    """Provides a mock argparse.Namespace object for tests."""
    # Use a real object that can have attributes set
    class MockArgs:
        def __init__(self):
            self.model = "default-model"
    return MockArgs()

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
    assert "/plan --edit <N> <text>" in captured.out
    assert "/skip" in captured.out
    assert "/settings" in captured.out
    assert "/show [goal|plan|context|history]" in captured.out

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

@patch('patchllm.tui.interface._run_settings_tui')
@patch('prompt_toolkit.PromptSession.prompt')
def test_tui_settings_command(mock_prompt, mock_settings_tui, temp_project):
    os.chdir(temp_project)
    mock_prompt.side_effect = ["/settings", "/exit"]
    with patch.object(sys, 'argv', ['patchllm']):
        main()
    # The TUI loop calls the settings function with the session and console objects
    mock_settings_tui.assert_called_once()


@patch('InquirerPy.prompt')
@patch('patchllm.tui.interface.AgentSession')
def test_tui_settings_change_model_flow(mock_agent_session, mock_inquirer_prompt, temp_project):
    os.chdir(temp_project)
    mock_session_instance = mock_agent_session.return_value
    
    # Simulate the sequence of choices in the settings TUI
    mock_inquirer_prompt.side_effect = [
        {"action": f"Change Model (current: {mock_session_instance.args.model})"},
        {"model": "ollama/test-model"},
        {"action": "Back to agent"}
    ]
    
    with patch('patchllm.tui.interface.model_list', ['ollama/test-model', 'gemini/flash']):
        # We call the function directly to test its internal logic
        from patchllm.tui.interface import _run_settings_tui, Console
        _run_settings_tui(mock_session_instance, Console())

    # Check that the session's model was updated
    assert mock_session_instance.args.model == "ollama/test-model"
    # Check that the change was persisted
    mock_session_instance.save_settings.assert_called_once()


@patch('patchllm.tui.interface.AgentSession')
@patch('prompt_toolkit.PromptSession.prompt')
def test_tui_plan_edit_command(mock_prompt, mock_agent_session, temp_project):
    os.chdir(temp_project)
    mock_session_instance = mock_agent_session.return_value
    mock_session_instance.plan = ["step 1"]
    mock_prompt.side_effect = ["/plan --edit 1 this is the new text", "/exit"]
    with patch.object(sys, 'argv', ['patchllm']):
        main()
    mock_session_instance.edit_plan_step.assert_called_once_with(1, "this is the new text")

@patch('patchllm.tui.interface.AgentSession')
@patch('prompt_toolkit.PromptSession.prompt')
def test_tui_plan_rm_command(mock_prompt, mock_agent_session, temp_project):
    os.chdir(temp_project)
    mock_session_instance = mock_agent_session.return_value
    mock_session_instance.plan = ["step 1"]
    mock_prompt.side_effect = ["/plan --rm 1", "/exit"]
    with patch.object(sys, 'argv', ['patchllm']):
        main()
    mock_session_instance.remove_plan_step.assert_called_once_with(1)

@patch('patchllm.tui.interface.AgentSession')
@patch('prompt_toolkit.PromptSession.prompt')
def test_tui_plan_add_command(mock_prompt, mock_agent_session, temp_project):
    os.chdir(temp_project)
    mock_session_instance = mock_agent_session.return_value
    mock_session_instance.plan = ["step 1"]
    mock_prompt.side_effect = ["/plan --add a new step", "/exit"]
    with patch.object(sys, 'argv', ['patchllm']):
        main()
    mock_session_instance.add_plan_step.assert_called_once_with("a new step")

@patch('patchllm.tui.interface.AgentSession')
@patch('prompt_toolkit.PromptSession.prompt')
def test_tui_skip_command(mock_prompt, mock_agent_session, temp_project):
    os.chdir(temp_project)
    mock_session_instance = mock_agent_session.return_value
    mock_session_instance.plan = ["step 1"]
    mock_prompt.side_effect = ["/skip", "/exit"]
    with patch.object(sys, 'argv', ['patchllm']):
        main()
    mock_session_instance.skip_step.assert_called_once()

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

@pytest.mark.parametrize("sub_command, session_data, expected_output, is_empty", [
    ("plan", {"plan": ["step 1"]}, "Execution Plan", False),
    ("plan", {"plan": []}, "No plan exists.", True),
    ("goal", {"goal": "my test goal"}, "Current Goal", False),
    ("goal", {"goal": None}, "No goal set.", True),
    ("history", {"action_history": ["did a thing"]}, "Session History", False),
    ("history", {"action_history": []}, "No actions recorded yet.", True),
    ("context", {"context_files": [Path("/fake/file.py")]}, "Context Tree", False),
    ("context", {"context_files": []}, "Context is empty.", True),
    ("invalid", {}, "Usage: /show", False),
])
@patch('patchllm.tui.interface.AgentSession')
@patch('prompt_toolkit.PromptSession.prompt')
def test_tui_show_commands(mock_prompt, mock_agent_session, temp_project, capsys, sub_command, session_data, expected_output, is_empty):
    os.chdir(temp_project)
    mock_session_instance = mock_agent_session.return_value
    
    # Set up the session state based on parametrized data
    for key, value in session_data.items():
        setattr(mock_session_instance, key, value)
    
    # If the session state is empty, ensure the mock reflects that
    if is_empty:
        for key in session_data.keys():
             # Handle None for goal specifically
            setattr(mock_session_instance, key, None if key == 'goal' else [])

    mock_prompt.side_effect = [f"/show {sub_command}", "/exit"]
    with patch.object(sys, 'argv', ['patchllm']):
        main()
    
    captured = capsys.readouterr()
    assert expected_output in captured.out