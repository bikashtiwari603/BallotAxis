import pytest
import os
from unittest.mock import MagicMock
import google.generativeai as genai

@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake_test_key_12345")
    # Mock genai.configure and genai.GenerativeModel
    monkeypatch.setattr(genai, "configure", lambda api_key: None)
    
    # Mock the GenerativeModel class
    mock_model = MagicMock()
    mock_chat = MagicMock()
    mock_response = MagicMock()
    
    mock_response.text = '{"response": "Test response from AI", "suggestions": ["Option 1", "Option 2"]}'
    mock_chat.send_message.return_value = mock_response
    mock_model.start_chat.return_value = mock_chat
    
    monkeypatch.setattr(genai, "GenerativeModel", lambda *args, **kwargs: mock_model)
