import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import os

pytest.importorskip("InquirerPy")

from patchllm.cli.entrypoint import main
from patchllm.chat.chat import ChatSession
from patchllm.utils import load_from_py_file

@pytest.fixture
def mock_prompts():
    """Fixture to mock all InquirerPy prompts."""
    with patch('patchllm.chat.chat.prompt') as mock:
        yield mock

@pytest.fixture
def mock_llm():
    """Fixture to mock the LLM query function."""
    with patch('patchllm.chat.chat.run_llm_query') as mock:
        yield mock

def test_chat_session_full_flow(mock_prompts, mock_llm, temp_project, temp_scopes_file):
    # --- Mocks Setup ---
    # 1. Scope selection
    # 2. Task input
    # 3. Confirmation to proceed
    # 4. Action selection after LLM response
    mock_prompts.side_effect = [
        ["base"],
        ["add a new feature"],
        [True],
        ["apply"]
    ]

    # Mock LLM returns a valid response to create a file
    new_file = temp_project / "new_feature.py"
    mock_llm.return_value = f"<file_path:{new_file.as_posix()}>\n```python\n# new feature code\n```"

    # --- Run Test ---
    os.chdir(temp_project)
    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
        # Using a direct class instance to avoid argparse complexity
        # CORRECTED: Added interactive=False to prevent ambiguity
        args = MagicMock(scope=None, model='mock-model', interactive=False)
        scopes = load_from_py_file(temp_scopes_file, "scopes")
        # FIX: Added the missing 'recipes' argument, passing an empty dict.
        session = ChatSession(args, scopes, {})
        session.start()

    # --- Assertions ---
    assert mock_prompts.call_count == 4
    mock_llm.assert_called_once()
    assert new_file.exists()
    assert new_file.read_text() == "# new feature code"
    assert args.scope == 'base' # Check that the arg object was updated

def test_chat_session_diff_and_cancel(mock_prompts, mock_llm, temp_project, temp_scopes_file, capsys):
    # --- Mocks Setup ---
    # 1. Scope -> 'base'
    # 2. Task -> 'update main.py'
    # 3. Confirm -> True
    # 4. Action -> 'diff'
    # 5. Nested Action after diff -> 'cancel'
    mock_prompts.side_effect = [
        ["base"],
        ["update main.py"],
        [True],
        ["diff"],
        ["cancel"]
    ]

    main_py = temp_project / "main.py"
    original_content = main_py.read_text()
    new_content = original_content + "\n# new line"
    mock_llm.return_value = f"<file_path:{main_py.as_posix()}>\n```python\n{new_content}\n```"

    # --- Run Test ---
    os.chdir(temp_project)
    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
        # CORRECTED: Added interactive=False
        args = MagicMock(scope=None, model='mock-model', interactive=False)
        scopes = load_from_py_file(temp_scopes_file, "scopes")
        # FIX: Added the missing 'recipes' argument, passing an empty dict.
        session = ChatSession(args, scopes, {})
        session.start()

    # --- Assertions ---
    assert mock_prompts.call_count == 5
    mock_llm.assert_called_once()
    # File should NOT have changed because we cancelled
    assert main_py.read_text() == original_content
    
    captured = capsys.readouterr()
    assert "--- Proposed Changes (Diff) ---" in captured.out
    assert "+# new line" in captured.out
    assert "Cancelled." in captured.out

def test_chat_flag_initiates_chat_flow(temp_project, temp_scopes_file):
    os.chdir(temp_project)
    # CORRECTED: The patch target must be where the function is looked up (entrypoint), not where it's defined.
    with patch('patchllm.cli.entrypoint.handle_chat_flow') as mock_handler:
        with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
            with patch('sys.argv', ['patchllm', '--chat']):
                 main()
    
    mock_handler.assert_called_once()