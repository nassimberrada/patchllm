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
        mock_wizard_prompts.side_effect = [
            {"source": "saved"},
            {"scope": "base"},
            {"action": "Proceed"},
            {"action": "Update code with LLM"},
        ]

        # --- CORRECTION: The list choice prompt returns a dict with the name of the prompt ---
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
    assert mock_wizard_prompts.call_count == 4
    assert mock_chat_prompts.call_count == 4
    mock_llm_for_wizard.assert_called_once()
    assert new_file.exists()
    assert new_file.read_text() == "# wizard code"

def test_wizard_save_to_file_flow(mock_wizard_prompts, temp_project, temp_scopes_file):
    # --- Mocks Setup ---
    output_file = temp_project / "wizard_context.md"
    
    mock_wizard_prompts.side_effect = [
        {"source": "saved"},
        {"scope": "js_and_css"},
        {"action": "Proceed"},
        {"action": "Save context to file"},
        {"path": str(output_file)}
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