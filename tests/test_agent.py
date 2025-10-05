import pytest
from pathlib import Path
import os
from unittest.mock import patch, MagicMock

from patchllm.agent.session import AgentSession
from patchllm.utils import load_from_py_file

@pytest.fixture
def mock_args():
    return MagicMock(model="mock-model")

def test_session_edit_plan_step(mock_args):
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.plan = ["step 1", "step 2", "step 3"]
    
    success = session.edit_plan_step(2, "step 2 edited")
    assert success is True
    assert session.plan == ["step 1", "step 2 edited", "step 3"]

    failure = session.edit_plan_step(5, "invalid")
    assert failure is False

def test_session_remove_plan_step(mock_args):
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.plan = ["step 1", "step 2", "step 3"]
    session.current_step = 2

    success = session.remove_plan_step(1)
    assert success is True
    assert session.plan == ["step 2", "step 3"]
    assert session.current_step == 1

    success_2 = session.remove_plan_step(2)
    assert success_2 is True
    assert session.plan == ["step 2"]
    assert session.current_step == 1

    failure = session.remove_plan_step(5)
    assert failure is False

def test_session_add_plan_step(mock_args):
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.plan = ["step 1"]
    session.add_plan_step("step 2")
    assert session.plan == ["step 1", "step 2"]

def test_session_skip_step(mock_args):
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.plan = ["step 1", "step 2"]
    session.last_execution_result = {"diffs": []}
    
    success = session.skip_step()
    assert success is True
    assert session.current_step == 1
    assert session.last_execution_result is None

    session.skip_step()
    assert session.current_step == 2

    failure = session.skip_step()
    assert failure is False

def test_session_approve_changes(mock_args):
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.plan = ["do something"]
    session.last_execution_result = { "instruction": "do something", "llm_response": "<file>..." }
    # --- FIX: Patch the function in its original module, not where it's used ---
    with patch('patchllm.parser.paste_response') as mock_paste:
        success = session.approve_changes()
        assert success is True
        mock_paste.assert_called_once_with("<file>...")
        assert session.current_step == 1
        assert session.last_execution_result is None

def test_session_retry_step(mock_args):
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.plan = ["original instruction"]
    # --- FIX: Patch the function in its original module, not where it's used ---
    with patch('patchllm.agent.executor.execute_step') as mock_exec:
        session.retry_step("it was wrong")
        mock_exec.assert_called_once()
        refined_instruction = mock_exec.call_args[0][0]
        assert "feedback: it was wrong" in refined_instruction
        assert "original instruction" in refined_instruction

# ... (rest of the test file is unchanged and correct) ...
def test_session_serialization_and_deserialization(mock_args, temp_project):
    os.chdir(temp_project)
    session1 = AgentSession(args=mock_args, scopes={}, recipes={})
    session1.set_goal("my goal")
    session1.plan = ["step 1", "step 2"]
    session1.current_step = 1
    file_path = temp_project / "main.py"
    file_path.write_text("content")
    session1.add_files_and_rebuild_context([file_path])
    session_data = session1.to_dict()
    session2 = AgentSession(args=mock_args, scopes={}, recipes={})
    session2.from_dict(session_data)
    assert session2.goal == session1.goal
    assert session2.plan == session1.plan
    assert session2.current_step == session1.current_step
    assert session2.context_files == session1.context_files
    assert "content" in session2.context