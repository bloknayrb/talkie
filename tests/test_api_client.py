"""Tests for api_client."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from talkie_modules.api_client import transcribe_audio, process_text_llm, _resolve_key
from talkie_modules.exceptions import TalkieAPIError, TalkieConfigError


class TestResolveKey:
    def test_from_config(self) -> None:
        config = {"openai_key": "sk-test123456789012345"}
        assert _resolve_key(config, "openai_key", "OPENAI_API_KEY") == "sk-test123456789012345"

    def test_from_env(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-env-key-12345678901"}):
            config = {"openai_key": ""}
            assert _resolve_key(config, "openai_key", "OPENAI_API_KEY") == "sk-env-key-12345678901"

    def test_missing_raises(self) -> None:
        with pytest.raises(TalkieConfigError, match="API key missing"):
            _resolve_key({}, "openai_key", "NONEXISTENT_VAR_12345")


class TestTranscribeAudio:
    def test_unsupported_provider(self) -> None:
        config = {"stt_provider": "azure", "models": {}}
        audio = np.zeros((1000, 1), dtype=np.float32)
        with pytest.raises(TalkieConfigError, match="Unsupported STT"):
            transcribe_audio(audio, config)

    @patch("talkie_modules.api_client._get_openai_client")
    def test_openai_stt(self, mock_get_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = MagicMock(text="Hello world")
        mock_get_client.return_value = mock_client

        config = {
            "stt_provider": "openai",
            "openai_key": "sk-test123456789012345",
            "models": {"openai_stt": "whisper-1"},
        }
        audio = np.zeros((16000, 1), dtype=np.float32)  # 1 second of silence

        result = transcribe_audio(audio, config)
        assert result == "Hello world"
        mock_client.audio.transcriptions.create.assert_called_once()


class TestProcessTextLLM:
    def test_unsupported_provider(self) -> None:
        config = {"api_provider": "azure", "models": {}, "snippets": {}, "system_prompt": "test"}
        with pytest.raises(TalkieConfigError, match="Unsupported LLM"):
            process_text_llm("hello", "context", config)

    @patch("talkie_modules.api_client._get_openai_client")
    def test_openai_llm(self, mock_get_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Processed text"))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        config = {
            "api_provider": "openai",
            "openai_key": "sk-test123456789012345",
            "models": {"openai_llm": "gpt-4o"},
            "snippets": {"gm": "Good morning"},
            "system_prompt": "Test prompt {snippets}",
        }

        result = process_text_llm("hello world", "previous text", config)
        assert result == "Processed text"

    @patch("talkie_modules.api_client._get_anthropic_client")
    def test_anthropic_llm(self, mock_get_client: MagicMock) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Claude response")]
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        config = {
            "api_provider": "anthropic",
            "anthropic_key": "sk-ant-test1234567890123",
            "models": {"anthropic_llm": "claude-sonnet-4-20250514"},
            "snippets": {},
            "system_prompt": "Test prompt {snippets}",
        }

        result = process_text_llm("hello", "context", config)
        assert result == "Claude response"
