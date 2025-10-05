import pytest
from unittest.mock import patch
from patchllm.agent.planner import generate_plan

@patch('patchllm.agent.planner.run_llm_query')
def test_generate_plan_parses_numbered_list(mock_run_llm_query):
    """
    Tests that the planner correctly parses a standard numbered list from the LLM.
    """
    mock_llm_response = """
Here is the plan:
1. First, modify the main.py file to add a new function.
2. Next, create a new file called new_utils.py.
3. Finally, update the README.md.
"""
    mock_run_llm_query.return_value = mock_llm_response
    
    plan = generate_plan("some goal", "some tree", "mock-model")
    
    assert plan is not None
    assert len(plan) == 3
    assert plan[0] == "First, modify the main.py file to add a new function."
    assert plan[1] == "Next, create a new file called new_utils.py."
    assert plan[2] == "Finally, update the README.md."
    mock_run_llm_query.assert_called_once()
    # Check that the prompt contains the goal and tree
    sent_messages = mock_run_llm_query.call_args[0][0]
    assert "## Goal:\nsome goal" in sent_messages[1]['content']
    assert "## Project Structure:\n```\nsome tree\n```" in sent_messages[1]['content']

@patch('patchllm.agent.planner.run_llm_query')
def test_generate_plan_handles_no_response(mock_run_llm_query):
    """
    Tests that the planner returns None if the LLM gives an empty response.
    """
    mock_run_llm_query.return_value = None
    plan = generate_plan("goal", "tree", "model")
    assert plan is None