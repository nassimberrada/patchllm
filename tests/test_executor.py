import pytest
from unittest.mock import patch
from patchllm.agent.executor import execute_step

@patch('patchllm.agent.executor.run_llm_query')
def test_execute_step_with_text_only(mock_run_llm_query):
    """Tests that execute_step sends a simple text prompt when no images are present."""
    mock_run_llm_query.return_value = (
        "<change_summary>Summary of changes.</change_summary>\n"
        "<file_path:/a.txt>\n```\n...```"
    )
    
    result = execute_step("test instruction", [], "test context", None, "gemini/gemini-1.5-flash")
    
    mock_run_llm_query.assert_called_once()
    messages = mock_run_llm_query.call_args[0][0]
    user_message = messages[-1]
    
    assert user_message["role"] == "user"
    assert isinstance(user_message["content"], list)
    assert len(user_message["content"]) == 1
    assert user_message["content"][0]["type"] == "text"
    assert "test instruction" in user_message["content"][0]["text"]
    assert "test context" in user_message["content"][0]["text"]
    
    assert result is not None
    assert result["change_summary"] == "Summary of changes."

@patch('patchllm.agent.executor.run_llm_query')
def test_execute_step_with_images(mock_run_llm_query):
    """Tests that execute_step constructs a multimodal prompt when images are present."""
    mock_run_llm_query.return_value = (
        "<change_summary>Image-related changes.</change_summary>\n"
        "<file_path:/a.txt>\n```\n...```"
    )
    
    mock_image_data = [{
        "mime_type": "image/png",
        "content_base64": "base64string"
    }]
    
    result = execute_step("test instruction", [], "test context", mock_image_data, "gemini/gemini-1.5-flash")
    
    mock_run_llm_query.assert_called_once()
    messages = mock_run_llm_query.call_args[0][0]
    user_message = messages[-1]
    
    assert user_message["role"] == "user"
    assert isinstance(user_message["content"], list)
    assert len(user_message["content"]) == 2 # 1 for text, 1 for image
    
    text_part = user_message["content"][0]
    assert text_part["type"] == "text"
    
    image_part = user_message["content"][1]
    assert image_part["type"] == "image_url"
    assert image_part["image_url"]["url"] == "data:image/png;base64,base64string"

    assert result is not None
    assert result["change_summary"] == "Image-related changes."