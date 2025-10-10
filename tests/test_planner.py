import pytest
from unittest.mock import patch
from patchllm.agent.planner import generate_plan_and_history, generate_refined_plan

@patch('patchllm.agent.planner.run_llm_query')
def test_generate_plan_and_history(mock_run_llm_query):
    """
    Tests that the planner returns the initial history and response correctly.
    """
    mock_llm_response = "1. First, modify the main.py file."
    mock_run_llm_query.return_value = mock_llm_response
    
    history, response = generate_plan_and_history("some goal", "some tree", "mock-model")
    
    assert response == mock_llm_response
    assert len(history) == 3 # System, User, Assistant
    assert history[2]['role'] == 'assistant'
    assert "## Goal:\nsome goal" in history[1]['content']
    assert "## Project Structure:\n```\nsome tree\n```" in history[1]['content']

@patch('patchllm.agent.planner.run_llm_query')
def test_generate_refined_plan(mock_run_llm_query):
    """
    Tests that the refine function correctly constructs a prompt with history and feedback.
    """
    initial_history = [
        {"role": "system", "content": "You are a planner."},
        {"role": "user", "content": "My goal is X."},
        {"role": "assistant", "content": "1. Do step 1."}
    ]
    feedback = "Actually, let's do step 2 first."

    mock_run_llm_query.return_value = "1. Do step 2.\n2. Do step 1."
    
    generate_refined_plan(initial_history, feedback, "mock-model")

    mock_run_llm_query.assert_called_once()
    sent_messages = mock_run_llm_query.call_args[0][0]
    
    # The sent messages should be the full history plus the new user feedback/instruction
    assert len(sent_messages) == 4
    assert sent_messages[0]['role'] == 'system'
    assert sent_messages[2]['content'] == "1. Do step 1."
    assert "## User Feedback:\nActually, let's do step 2 first." in sent_messages[3]['content']

@patch('patchllm.agent.planner.run_llm_query')
def test_generate_plan_handles_no_response(mock_run_llm_query):
    """
    Tests that the planner returns None if the LLM gives an empty response.
    """
    mock_run_llm_query.return_value = None
    _, response = generate_plan_and_history("goal", "tree", "model")
    assert response is None