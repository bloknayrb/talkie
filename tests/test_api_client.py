"""Tests for api_client."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from talkie_modules import api_client
from talkie_modules.api_client import transcribe_audio, process_text_llm, _resolve_key
from talkie_modules.exceptions import TalkieAPIError, TalkieConfigError


@pytest.fixture(autouse=True)
def _clear_client_cache():
    """Prevent cached SDK clients from leaking between tests."""
    api_client._client_cache.clear()
    yield
    api_client._client_cache.clear()


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
    def test_unknown_provider(self) -> None:
        config = {"stt_provider": "azure", "models": {}}
        audio = np.zeros((1000, 1), dtype=np.float32)
        with pytest.raises(TalkieConfigError, match="Unknown STT provider"):
            transcribe_audio(audio, config)

    def test_no_stt_support(self) -> None:
        config = {"stt_provider": "anthropic", "models": {}}
        audio = np.zeros((1000, 1), dtype=np.float32)
        with pytest.raises(TalkieConfigError, match="does not support STT"):
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


def _openai_llm_config(**overrides: object) -> dict:
    """Minimal OpenAI LLM config for tests."""
    config: dict = {
        "api_provider": "openai",
        "openai_key": "sk-test123456789012345",
        "models": {"openai_llm": "gpt-4o"},
        "snippets": {},
        "custom_vocabulary": [],
        "system_prompt": "Test {snippets} {vocabulary}",
    }
    config.update(overrides)
    return config


def _mock_openai_completion(mock_get_client: MagicMock, text: str = "Result") -> MagicMock:
    """Wire up a mock OpenAI client that returns `text`."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=text))]
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client
    return mock_client


class TestProcessTextLLM:
    def test_unknown_provider(self) -> None:
        config = {"api_provider": "azure", "models": {}, "snippets": {}, "system_prompt": "test"}
        with pytest.raises(TalkieConfigError, match="Unknown LLM provider"):
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
            "custom_vocabulary": ["Talkie"],
            "system_prompt": "Test prompt {snippets} {vocabulary}",
        }

        result = process_text_llm("hello world", "previous text", config)
        assert result == "Processed text"

        # Verify both placeholders were substituted in the system prompt
        call_args = mock_client.chat.completions.create.call_args
        system_msg = call_args[1]["messages"][0]["content"]
        assert "{snippets}" not in system_msg
        assert "{vocabulary}" not in system_msg
        assert "Talkie" in system_msg
        assert "'gm' to 'Good morning'" in system_msg

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
            "custom_vocabulary": [],
            "system_prompt": "Test prompt {snippets} {vocabulary}",
        }

        result = process_text_llm("hello", "context", config)
        assert result == "Claude response"

        # Verify empty snippets/vocabulary produce "(none)"
        call_args = mock_client.messages.create.call_args
        system_content = call_args[1]["system"]
        assert "(none)" in system_content
        assert "{snippets}" not in system_content
        assert "{vocabulary}" not in system_content

    @patch("talkie_modules.api_client._get_openai_client")
    def test_prompt_without_vocabulary_placeholder(self, mock_get_client: MagicMock) -> None:
        """Old prompts without {vocabulary} should work — .replace() is a no-op."""
        mock_client = _mock_openai_completion(mock_get_client)
        config = _openai_llm_config(
            custom_vocabulary=["Talkie", "Wispr Flow"],
            system_prompt="Old prompt with only {snippets} placeholder",
        )

        result = process_text_llm("hello", "context", config)
        assert result == "Result"

        # Verify no literal {vocabulary} leaked into prompt
        call_args = mock_client.chat.completions.create.call_args
        system_msg = call_args[1]["messages"][0]["content"]
        assert "{vocabulary}" not in system_msg
        assert "Talkie" not in system_msg  # vocabulary not injected without placeholder

    @patch("talkie_modules.api_client._get_openai_client")
    def test_app_context_included_when_provided(self, mock_get_client: MagicMock) -> None:
        """App context tag appears in user prompt when process/title are given."""
        mock_client = _mock_openai_completion(mock_get_client)

        process_text_llm(
            "hello", "ctx", _openai_llm_config(),
            process_name="Code.exe", window_title="main.py - VS Code",
        )

        call_args = mock_client.chat.completions.create.call_args
        user_msg = call_args[1]["messages"][1]["content"]
        assert "<app_context>" in user_msg
        assert "Code.exe" in user_msg
        assert "main.py - VS Code" in user_msg

    @patch("talkie_modules.api_client._get_openai_client")
    def test_app_context_omitted_when_empty(self, mock_get_client: MagicMock) -> None:
        """No app_context tag when both process_name and window_title are empty."""
        mock_client = _mock_openai_completion(mock_get_client)

        process_text_llm("hello", "ctx", _openai_llm_config())

        call_args = mock_client.chat.completions.create.call_args
        user_msg = call_args[1]["messages"][1]["content"]
        assert "<app_context>" not in user_msg
