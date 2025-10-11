import pytest
from pathlib import Path
import os
import json
from unittest.mock import patch, MagicMock

from patchllm.agent.session import AgentSession, CONFIG_FILE_PATH
from patchllm.utils import load_from_py_file

@pytest.fixture
def mock_args():
    class MockArgs:
        def __init__(self, model="default-model"):
            self.model = model
    return MockArgs()

def test_session_ask_question_about_plan(mock_args):
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.plan = ["step 1"]
    session.planning_history = [{"role": "system", "content": "You are a planner."}]
    
    with patch('patchllm.llm.run_llm_query') as mock_llm:
        mock_llm.return_value = "This is the answer."
        response = session.ask_question("Why step 1?")
        
        assert response == "This is the answer."
        assert len(session.planning_history) == 2 # System, Assistant (user is not stored)
        
        # Check the call to the mock
        mock_llm.assert_called_once()
        sent_messages = mock_llm.call_args[0][0]
        user_message_content = sent_messages[-1]['content'][0]['text']
        
        assert "My Question" in user_message_content
        assert "Why step 1?" in user_message_content
        assert "Code Context" not in user_message_content
        
        assert session.planning_history[-1]['content'] == "This is the answer."
        assert session.plan == ["step 1"]


def test_session_ask_question_about_context(mock_args):
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.context = "<file_path:/app.py>..."
    session.planning_history = [{"role": "system", "content": "You are a planner."}]
    
    with patch('patchllm.llm.run_llm_query') as mock_llm:
        mock_llm.return_value = "It's a web server."
        response = session.ask_question("What does app.py do?")
        
        assert response == "It's a web server."
        assert len(session.planning_history) == 2
        
        mock_llm.assert_called_once()
        sent_messages = mock_llm.call_args[0][0]
        prompt_content = sent_messages[-1]['content'][0]['text']
        
        assert "Code Context" in prompt_content
        assert "<file_path:/app.py>..." in prompt_content
        assert "My Question" in prompt_content
        assert "What does app.py do?" in prompt_content

def test_session_ask_question_with_image(mock_args):
    """Ensures that ask_question sends image data correctly."""
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.context = "Some text context"
    session.context_images = [{
        "mime_type": "image/png",
        "content_base64": "base64string"
    }]
    
    with patch('patchllm.llm.run_llm_query') as mock_llm:
        mock_llm.return_value = "It's an image."
        session.ask_question("What is this?")
        
        mock_llm.assert_called_once()
        sent_messages = mock_llm.call_args[0][0]
        user_message_content = sent_messages[-1]['content']
        
        assert isinstance(user_message_content, list)
        assert len(user_message_content) == 2
        
        text_part = user_message_content[0]
        assert text_part['type'] == 'text'
        assert "What is this?" in text_part['text']
        
        image_part = user_message_content[1]
        assert image_part['type'] == 'image_url'
        assert image_part['image_url']['url'] == "data:image/png;base64,base64string"

def test_session_refine_plan(mock_args):
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.plan = ["old step 1"]
    session.planning_history = [{"role": "system", "content": "Planner"}]
    
    with patch('patchllm.agent.planner.generate_refined_plan') as mock_refiner:
        mock_refiner.return_value = "1. new step 1\n2. new step 2"
        success = session.refine_plan("Please add another step.")

        assert success is True
        assert session.plan == ["new step 1", "new step 2"]
        assert len(session.planning_history) == 3
        mock_refiner.assert_called_once()

def test_session_load_and_save_settings(mock_args, tmp_path):
    os.chdir(tmp_path)
    session1 = AgentSession(args=mock_args, scopes={}, recipes={})
    session1.args.model = "new-saved-model"
    session1.save_settings()
    
    assert CONFIG_FILE_PATH.exists()
    with open(CONFIG_FILE_PATH, 'r') as f:
        data = json.load(f)
    assert data['model'] == "new-saved-model"

    session2 = AgentSession(args=mock_args, scopes={}, recipes={})
    assert session2.args.model == "new-saved-model"

    CONFIG_FILE_PATH.unlink()
    mock_args.model = "default-model" 
    session3 = AgentSession(args=mock_args, scopes={}, recipes={})
    assert session3.args.model == "default-model"


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

def test_session_approve_changes_full(mock_args):
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.plan = ["do something"]
    llm_response = "<file_path:/tmp/a.txt>\n```python\nprint('hello')\n```"
    session.last_execution_result = {
        "instruction": "do something",
        "llm_response": llm_response,
        "summary": {"modified": ["/tmp/a.txt"], "created": []}
    }
    with patch('patchllm.parser.paste_response_selectively') as mock_paste:
        is_full_approval = session.approve_changes(["/tmp/a.txt"])
        assert is_full_approval is True
        mock_paste.assert_called_once_with(llm_response, ["/tmp/a.txt"])
        assert session.current_step == 1
        assert session.last_execution_result is None

def test_session_approve_changes_partial(mock_args):
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.plan = ["do something"]
    llm_response = "<file_path:/tmp/a.txt>\n```\n...\n```<file_path:/tmp/b.txt>\n```\n...\n```"
    session.last_execution_result = {
        "instruction": "do something",
        "llm_response": llm_response,
        "summary": {"modified": ["/tmp/a.txt", "/tmp/b.txt"], "created": []}
    }
    with patch('patchllm.parser.paste_response_selectively') as mock_paste:
        is_full_approval = session.approve_changes(["/tmp/a.txt"])
        assert is_full_approval is False
        mock_paste.assert_called_once_with(llm_response, ["/tmp/a.txt"])
        assert session.current_step == 0
        assert session.last_execution_result is not None
        assert session.last_execution_result['approved_files'] == ["/tmp/a.txt"]

def test_session_retry_step_after_partial_approval(mock_args):
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.plan = ["original instruction"]
    session.last_execution_result = {
        "approved_files": ["/tmp/a.txt"],
        "summary": {"modified": ["/tmp/a.txt", "/tmp/b.txt"], "created": []}
    }
    with patch('patchllm.agent.executor.execute_step') as mock_exec:
        session.retry_step("it was wrong")
        mock_exec.assert_called_once()
        refined_instruction = mock_exec.call_args[0][0]
        assert "I have **approved** the changes" in refined_instruction
        assert "a.txt" in refined_instruction
        assert "I **rejected** the changes" in refined_instruction
        assert "b.txt" in refined_instruction
        assert "feedback on the rejected files: it was wrong" in refined_instruction
        assert "original overall instruction" in refined_instruction

def test_session_retry_step(mock_args):
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.plan = ["original instruction"]
    with patch('patchllm.agent.executor.execute_step') as mock_exec:
        session.retry_step("it was wrong")
        mock_exec.assert_called_once()
        refined_instruction = mock_exec.call_args[0][0]
        assert "feedback: it was wrong" in refined_instruction
        assert "original instruction" in refined_instruction

def test_session_serialization_and_deserialization(mock_args, temp_project):
    os.chdir(temp_project)
    session1 = AgentSession(args=mock_args, scopes={}, recipes={})
    session1.set_goal("my goal")
    session1.plan = ["step 1", "step 2"]
    session1.current_step = 1
    session1.action_history = ["Goal set: my goal"]
    session1.last_revert_state = [{"file_path": "/tmp/a.txt", "content": "old", "action": "modify"}]
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
    assert session2.action_history == session1.action_history
    assert session2.last_revert_state == session1.last_revert_state

def test_session_action_history(mock_args):
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.set_goal("My test goal")
    assert len(session.action_history) == 1

    with patch('patchllm.agent.planner.generate_plan_and_history') as mock_planner:
        mock_planner.return_value = ([{"role": "user", "content": ""}], "1. Do a thing")
        session.create_plan()
    assert len(session.action_history) == 2

    session.last_execution_result = {"llm_response": "...", "summary": {"modified": ["/tmp/a.txt"], "created": []}}
    session.approve_changes(["/tmp/a.txt"])
    assert len(session.action_history) == 3
    assert "Approved 1 file(s)" in session.action_history[2]

    session.revert_last_approval()
    assert len(session.action_history) == 4
    assert "Reverted" in session.action_history[3]

def test_session_revert_last_approval(mock_args, tmp_path):
    os.chdir(tmp_path)
    
    file_to_modify = tmp_path / "test.py"
    original_content = "def hello_world():\n    return 'original'"
    file_to_modify.write_text(original_content)

    file_to_create = tmp_path / "new_file.py"
    
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.current_step = 0
    session.plan = ["Modify test.py and create new_file.py"]
    
    new_content_modify = "def hello_world():\n    return 'modified'"
    new_content_create = "print('new file')"
    
    llm_response = (
        f"<file_path:{file_to_modify.as_posix()}>\n```python\n{new_content_modify}\n```\n"
        f"<file_path:{file_to_create.as_posix()}>\n```python\n{new_content_create}\n```"
    )
    session.last_execution_result = {"llm_response": llm_response, "summary": {"modified": [file_to_modify.as_posix()], "created": [file_to_create.as_posix()]}}
    
    session.approve_changes([file_to_modify.as_posix(), file_to_create.as_posix()])
    assert file_to_modify.read_text() == new_content_modify
    assert file_to_create.read_text() == new_content_create
    assert len(session.last_revert_state) == 2
    
    success_revert = session.revert_last_approval()
    assert success_revert is True
    
    assert file_to_modify.read_text() == original_content
    assert not file_to_create.exists()
    assert session.last_revert_state == []

def test_session_load_context_with_image(mock_args, temp_project):
    """Tests that loading a scope with an image populates context_images."""
    os.chdir(temp_project)
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    
    # We use a dynamic scope that will just grab everything in the directory
    session.load_context_from_scope(f"@dir:{temp_project.as_posix()}")

    assert session.context is not None
    assert "main.py" in session.context
    
    assert session.context_images is not None
    assert len(session.context_images) == 1
    assert session.context_images[0]["path"].name == "logo.png"

def test_session_run_goal_directly(mock_args):
    """Tests executing a goal without a plan."""
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.set_goal("my goal")
    with patch('patchllm.agent.executor.execute_step') as mock_exec:
        mock_exec.return_value = {"summary": {}}
        session.run_goal_directly()
        
        mock_exec.assert_called_once()
        instruction = mock_exec.call_args[0][0]
        assert "achieve the following goal" in instruction
        assert "my goal" in instruction
        
        assert session.last_execution_result is not None
        assert session.last_execution_result['is_planless_run'] is True

def test_session_approve_changes_planless_run(mock_args):
    """Tests that approving a planless run does not advance a step count."""
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.set_goal("my goal")
    llm_response = "<file_path:/a.txt>\n```\n...\n```"
    session.last_execution_result = {
        "instruction": "...",
        "llm_response": llm_response,
        "summary": {"modified": ["/a.txt"], "created": []},
        "is_planless_run": True
    }
    
    with patch('patchllm.parser.paste_response_selectively'):
        is_full_approval = session.approve_changes(["/a.txt"])
        
        assert is_full_approval is True
        assert session.current_step == 0 # Should NOT have changed
        assert session.last_execution_result is None
        assert "plan-less goal execution" in session.action_history[-1]

def test_session_retry_step_planless_partial_approval(mock_args):
    """Tests retrying a planless run after a partial approval."""
    session = AgentSession(args=mock_args, scopes={}, recipes={})
    session.set_goal("my goal")
    session.last_execution_result = {
        "approved_files": ["a.txt"],
        "summary": {"modified": ["a.txt", "b.txt"], "created": []},
        "is_planless_run": True
    }
    with patch('patchllm.agent.executor.execute_step') as mock_exec:
        session.retry_step("feedback for b")
        
        mock_exec.assert_called_once()
        instruction = mock_exec.call_args[0][0]
        assert "approved** the changes for the following files:\n- a.txt" in instruction
        assert "rejected** the changes for these files:\n- b.txt" in instruction
        assert "feedback on the rejected files: feedback for b" in instruction
        assert "achieve the goal: my goal" in instruction