import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import os
import sys

pytest.importorskip("InquirerPy")

from patchllm.cli.entrypoint import main
from patchllm.utils import load_from_py_file

@pytest.fixture
def mock_wizard_prompts():
    """Fixture to mock all InquirerPy prompts in the handlers module."""
    with patch('patchllm.cli.handlers.prompt') as mock:
        yield mock

@pytest.fixture
def mock_llm_for_wizard():
    """Fixture to mock the LLM query function where it is called."""
    with patch('patchllm.chat.chat.run_llm_query') as mock:
        yield mock

def test_no_args_triggers_wizard_flow(temp_project):
    os.chdir(temp_project)
    with patch('patchllm.cli.entrypoint.handle_interactive_wizard_flow') as mock_handler:
        with patch.object(sys, 'argv', ['patchllm']):
            main()
    mock_handler.assert_called_once()

def test_wizard_full_update_code_flow(mock_wizard_prompts, mock_llm_for_wizard, temp_project, temp_scopes_file, temp_recipes_file):
    # --- Mocks Setup ---
    new_file = temp_project / "new_wizard_file.py"
    mock_llm_for_wizard.return_value = f"<file_path:{new_file.as_posix()}>\n```python\n# wizard code\n```"
    
    with patch('patchllm.chat.chat.prompt') as mock_chat_prompts:
        # --- Add main menu selection and exit choice to the prompt sequence ---
        mock_wizard_prompts.side_effect = [
            {"action": "new_task"},          # Main Menu: Select "Start new task"
            {"source": "saved"},             # Context Source: Select "saved scopes"
            {"scope": "base"},               # Scope Selection
            {"action": "Proceed"},           # Refine Context: Select "Proceed"
            {"action": "Update code with LLM"}, # Final Action -> breaks inner loop
            {"action": "exit"},              # Main Menu: Select "Exit" to terminate outer loop
        ]

        mock_chat_prompts.side_effect = [
            {"choice": ("manual", None)}, # Task or Recipe choice
            {"task": "create a new file"},  # Manual task input
            {"confirm": True},             # Confirm proceed
            {"action": "apply"}            # Action choice
        ]

        # --- Run Test ---
        os.chdir(temp_project)
        with patch.dict('os.environ', {
            'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix(),
            'PATCHLLM_RECIPES_FILE': temp_recipes_file.as_posix()
        }):
            with patch.object(sys, 'argv', ['patchllm']):
                main()

    # --- Assertions ---
    # Corrected the expected call count from 5 to 6.
    assert mock_wizard_prompts.call_count == 6
    assert mock_chat_prompts.call_count == 4
    mock_llm_for_wizard.assert_called_once()
    assert new_file.exists()
    assert new_file.read_text() == "# wizard code"

def test_wizard_save_to_file_flow(mock_wizard_prompts, temp_project, temp_scopes_file):
    # --- Mocks Setup ---
    output_file = temp_project / "wizard_context.md"
    
    mock_wizard_prompts.side_effect = [
        {"action": "new_task"},               # Main Menu: Select "Start new task"
        {"source": "saved"},                  # Context Source: "saved"
        {"scope": "js_and_css"},              # Scope Selection
        {"action": "Proceed"},                # Refine Context: "Proceed"
        {"action": "Save context to file"},   # Final Action
        {"path": str(output_file)},           # File path for saving
        {"action": "back"},                   # Back to main menu from action menu
        {"action": "exit"},                   # Main Menu: "Exit"
    ]

    # --- Run Test ---
    os.chdir(temp_project)
    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
        with patch.object(sys, 'argv', ['patchllm']):
            main()

    # --- Assertions ---
    assert output_file.exists()
    content = output_file.read_text()
    assert "src/component.js" in content
    assert "src/styles.css" in content
    assert "main.py" not in content

def test_wizard_scope_management_flow(mock_wizard_prompts, temp_scopes_file, capsys):
    # --- Mocks Setup ---
    mock_wizard_prompts.side_effect = [
        {"action": "manage_scopes"},
        {"action": "List scopes"},
        {"action": "exit"},
    ]

    # --- Run Test ---
    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
        with patch.object(sys, 'argv', ['patchllm']):
            main()

    # --- Assertions ---
    captured = capsys.readouterr()
    assert "Available scopes" in captured.out
    assert "base" in captured.out
    assert "js_and_css" in captured.out

def test_wizard_exit_flow(mock_wizard_prompts, capsys):
    # --- Mocks Setup ---
    mock_wizard_prompts.side_effect = [{"action": "exit"}]

    # --- Run Test ---
    with patch.object(sys, 'argv', ['patchllm']):
        main()

    # --- Assertions ---
    captured = capsys.readouterr()
    assert "Exiting PatchLLM Wizard" in captured.out
    assert "How would you like to build the context?" not in captured.out

def test_wizard_save_as_scope_flow(mock_wizard_prompts, temp_project, temp_scopes_file):
    # --- Setup ---
    os.chdir(temp_project)
    
    mock_wizard_prompts.side_effect = [
        # Main Menu
        {"action": "new_task"},
        # Context building: select the 'js_and_css' scope
        {"source": "saved"},
        {"scope": "js_and_css"},
        # Context refinement
        {"action": "Proceed"},
        # Context action menu (first loop): Save the context
        {"action": "Save this context as a new scope"},
        {"name": "my_web_files"}, # Provide name for the new scope
        # Context action menu (second loop): Go back
        {"action": "back"},
        # Main Menu
        {"action": "exit"},
    ]

    # --- Run Test ---
    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
        with patch.object(sys, 'argv', ['patchllm']):
            main()

    # --- Assertions ---
    updated_scopes = load_from_py_file(temp_scopes_file, "scopes")

    assert "my_web_files" in updated_scopes
    
    new_scope_data = updated_scopes["my_web_files"]
    assert new_scope_data["path"] == "."
    
    expected_files = sorted(['src/component.js', 'src/styles.css'])
    assert sorted(new_scope_data["include_patterns"]) == expected_files
    assert new_scope_data["exclude_patterns"] == []