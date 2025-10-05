import pytest
from pathlib import Path
import os
from unittest.mock import patch, MagicMock

from patchllm.agent.session import AgentSession
from patchllm.utils import load_from_py_file

@pytest.fixture
def mock_args():
    return MagicMock(model="mock-model")

# --- Tests from Phase 3 ---
def test_session_set_goal(mock_args):
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.plan = ["old step"]
    session.set_goal("new goal")
    assert session.goal == "new goal"
    assert session.plan == []

@patch('patchllm.agent.session.planner.generate_plan')
def test_session_create_plan_success(mock_generate_plan, mock_args, temp_project):
    os.chdir(temp_project)
    mock_plan = ["step 1", "step 2"]
    mock_generate_plan.return_value = mock_plan
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.set_goal("a task")
    success = session.create_plan()
    assert success is True
    assert session.plan == mock_plan

@patch('patchllm.agent.session.executor.execute_step')
def test_session_run_current_step_stores_result(mock_execute_step, mock_args):
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.plan = ["do something"]
    mock_result = {"llm_response": "...", "summary": {}, "diffs": []}
    mock_execute_step.return_value = mock_result
    result = session.run_current_step()
    assert result == mock_result
    assert session.last_execution_result == mock_result
    # State should NOT be advanced yet
    assert session.current_step == 0
    assert len(session.history) == 1 

# --- New Tests for Phase 4 ---

@patch('patchllm.agent.session.paste_response')
def test_session_approve_changes(mock_paste_response, mock_args):
    """
    Tests that approving changes applies the patch, updates history, and advances the plan.
    """
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.plan = ["do something"]
    session.current_step = 0
    session.last_execution_result = {
        "instruction": "do something",
        "llm_response": "<file_path:a.py>...",
        "summary": {}, "diffs": []
    }
    
    success = session.approve_changes()
    
    assert success is True
    mock_paste_response.assert_called_once_with("<file_path:a.py>...")
    
    # State should now be advanced
    assert session.current_step == 1
    assert session.last_execution_result is None
    assert len(session.history) == 3 # system, user, assistant
    assert "My task was: do something" in session.history[1]["content"]

@patch('patchllm.agent.session.executor.execute_step')
def test_session_retry_step(mock_execute_step, mock_args):
    """
    Tests that retrying a step calls the executor with a refined instruction.
    """
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.plan = ["original instruction"]
    session.current_step = 0
    
    # Mock the return value for the retry attempt
    mock_retry_result = {"llm_response": "new response"}
    mock_execute_step.return_value = mock_retry_result
    
    result = session.retry_step("it was wrong")
    
    assert result == mock_retry_result
    # The result of the retry is now stored, ready for approval
    assert session.last_execution_result == mock_retry_result
    
    # State should not be advanced
    assert session.current_step == 0
    assert len(session.history) == 1 # History is not updated until approve
    
    # Check that the executor was called with the refined prompt
    mock_execute_step.assert_called_once()
    call_args = mock_execute_step.call_args[0]
    refined_instruction = call_args[0]
    assert "feedback: it was wrong" in refined_instruction
    assert "original instruction was: original instruction" in refined_instruction

# --- Tests from Phase 2 ---
def test_session_load_context_from_scope(mock_args, temp_project, temp_scopes_file):
    os.chdir(temp_project)
    scopes = load_from_py_file(temp_scopes_file, "scopes")
    session = AgentSession(args=mock_args, scopes=scopes, recipes={})
    summary = session.load_context_from_scope("base")
    assert "main.py" in summary
    assert session.context is not None

def test_session_add_files_and_rebuild_context(mock_args, temp_project, temp_scopes_file):
    os.chdir(temp_project)
    scopes = load_from_py_file(temp_scopes_file, "scopes")
    session = AgentSession(args=mock_args, scopes=scopes, recipes={})
    session.load_context_from_scope("base")
    readme_path = temp_project / "README.md"
    summary = session.add_files_and_rebuild_context([readme_path])
    assert len(session.context_files) == 3
    assert "# Test Project" in session.context