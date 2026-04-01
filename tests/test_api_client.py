"""Tests for api_client."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from talkie_modules import api_client
from talkie_modules.api_client import (
    transcribe_audio,
    process_text_llm,
    test_connection as check_connection,
    _resolve_key,
)
from talkie_modules.exceptions import TalkieAPIError, TalkieConfigError


@pytest.fixture(autouse=True)
def _clear_client_cache():
    """Prevent cached SDK clients from leaking between tests."""
    api_client._client_cache.clear()
    yield
    api_client._client_cache.clear()


class TestResolveKey:
    _OPENAI_INFO = {"requires_key": True, "key_name": "openai_key", "key_env": "OPENAI_API_KEY"}

    def test_from_config(self) -> None:
        config = {"openai_key": "sk-test123456789012345"}
        assert _resolve_key(config, self._OPENAI_INFO) == "sk-test123456789012345"

    def test_from_env(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-env-key-12345678901"}):
            config = {"openai_key": ""}
            assert _resolve_key(config, self._OPENAI_INFO) == "sk-env-key-12345678901"

    def test_missing_raises(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            # Ensure the env var isn't set
            import os
            os.environ.pop("OPENAI_API_KEY", None)
            with pytest.raises(TalkieConfigError, match="API key missing"):
                _resolve_key({}, self._OPENAI_INFO)

    def test_keyless_provider_returns_empty(self) -> None:
        info = {"requires_key": False}
        assert _resolve_key({}, info) == ""


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


class TestCleanContextEcho:
    """Tests for _clean() stripping of echoed app_context from LLM responses."""

    _PROCESS = "Code.exe"
    _TITLE = "main.py - VS Code"
    _CTX = f'process="{_PROCESS}" title="{_TITLE}"'

    @patch("talkie_modules.api_client._get_openai_client")
    def test_strips_exact_prefix_echo(self, mock_get_client: MagicMock) -> None:
        """Exact app_context at position 0 is stripped."""
        _mock_openai_completion(mock_get_client, text=f"{self._CTX} Here is the real text")
        result = process_text_llm(
            "hello", "ctx", _openai_llm_config(),
            process_name=self._PROCESS, window_title=self._TITLE,
        )
        assert result == "Here is the real text"

    @patch("talkie_modules.api_client._get_openai_client")
    def test_strips_echo_with_leading_junk(self, mock_get_client: MagicMock) -> None:
        """Echo preceded by a few junk characters (the original bug) is stripped."""
        _mock_openai_completion(mock_get_client, text=f"0 {self._CTX} Cleaned output")
        result = process_text_llm(
            "hello", "ctx", _openai_llm_config(),
            process_name=self._PROCESS, window_title=self._TITLE,
        )
        assert result == "Cleaned output"

    @patch("talkie_modules.api_client._get_openai_client")
    def test_does_not_strip_deep_echo(self, mock_get_client: MagicMock) -> None:
        """Context string far into the response body is NOT stripped."""
        padding = "A" * len(self._CTX)  # pushes idx to exactly len(app_context_str)
        raw = f"{padding}{self._CTX} trailing"
        _mock_openai_completion(mock_get_client, text=raw)
        result = process_text_llm(
            "hello", "ctx", _openai_llm_config(),
            process_name=self._PROCESS, window_title=self._TITLE,
        )
        assert result == raw.strip()

    @patch("talkie_modules.api_client._get_openai_client")
    def test_boundary_max_proximity(self, mock_get_client: MagicMock) -> None:
        """idx == len(app_context_str) - 1 is the last offset that triggers stripping."""
        padding = "X" * (len(self._CTX) - 1)
        _mock_openai_completion(mock_get_client, text=f"{padding}{self._CTX} result")
        result = process_text_llm(
            "hello", "ctx", _openai_llm_config(),
            process_name=self._PROCESS, window_title=self._TITLE,
        )
        assert result == "result"

    @patch("talkie_modules.api_client._get_openai_client")
    def test_no_strip_when_no_context(self, mock_get_client: MagicMock) -> None:
        """Without process_name/window_title, _clean() only applies .strip()."""
        _mock_openai_completion(mock_get_client, text="  Clean text  ")
        result = process_text_llm("hello", "ctx", _openai_llm_config())
        assert result == "Clean text"

    @patch("talkie_modules.api_client._get_openai_client")
    def test_no_echo_with_context(self, mock_get_client: MagicMock) -> None:
        """When context is provided but LLM doesn't echo it, text passes through."""
        _mock_openai_completion(mock_get_client, text="Normal response text")
        result = process_text_llm(
            "hello", "ctx", _openai_llm_config(),
            process_name=self._PROCESS, window_title=self._TITLE,
        )
        assert result == "Normal response text"

    @patch("talkie_modules.api_client._get_openai_client")
    def test_empty_response(self, mock_get_client: MagicMock) -> None:
        """Empty LLM response returns empty string."""
        _mock_openai_completion(mock_get_client, text="")
        result = process_text_llm(
            "hello", "ctx", _openai_llm_config(),
            process_name=self._PROCESS, window_title=self._TITLE,
        )
        assert result == ""

    @patch("talkie_modules.api_client._get_openai_client")
    def test_partial_context_not_stripped(self, mock_get_client: MagicMock) -> None:
        """A partial app_context match (only process, no title) is not stripped."""
        _mock_openai_completion(
            mock_get_client, text=f'process="{self._PROCESS}" is running fine',
        )
        result = process_text_llm(
            "hello", "ctx", _openai_llm_config(),
            process_name=self._PROCESS, window_title=self._TITLE,
        )
        assert f'process="{self._PROCESS}"' in result


class TestLocalWhisperDispatch:
    @patch("talkie_modules.local_whisper.transcribe")
    def test_dispatches_to_local_whisper(self, mock_local: MagicMock) -> None:
        mock_local.return_value = "local result"
        config = {"stt_provider": "local_whisper", "models": {"local_whisper_stt": "tiny"}}
        audio = np.zeros((16000, 1), dtype=np.float32)
        result = transcribe_audio(audio, config)
        assert result == "local result"
        mock_local.assert_called_once_with(audio, "tiny")

    @patch("talkie_modules.local_whisper.transcribe")
    def test_uses_default_model(self, mock_local: MagicMock) -> None:
        mock_local.return_value = "result"
        config = {"stt_provider": "local_whisper", "models": {}}
        audio = np.zeros((16000, 1), dtype=np.float32)
        transcribe_audio(audio, config)
        # default_stt for local_whisper is "small"
        mock_local.assert_called_once_with(audio, "small")


class TestTestConnection:
    @patch("talkie_modules.local_whisper.is_binary_available", return_value=False)
    def test_local_whisper_no_binary(self, _mock: MagicMock) -> None:
        with pytest.raises(TalkieConfigError, match="Whisper engine not downloaded"):
            check_connection("local_whisper")

    @patch("talkie_modules.local_whisper.get_downloaded_models", return_value=[])
    @patch("talkie_modules.local_whisper.is_binary_available", return_value=True)
    def test_local_whisper_no_models(self, _m1: MagicMock, _m2: MagicMock) -> None:
        with pytest.raises(TalkieConfigError, match="No whisper models downloaded"):
            check_connection("local_whisper")

    @patch("talkie_modules.local_whisper.get_downloaded_models", return_value=["small"])
    @patch("talkie_modules.local_whisper.is_binary_available", return_value=True)
    def test_local_whisper_ok(self, _m1: MagicMock, _m2: MagicMock) -> None:
        check_connection("local_whisper")  # should not raise

    @patch("talkie_modules.ollama_utils.is_running", return_value=False)
    def test_ollama_not_running(self, _mock: MagicMock) -> None:
        with pytest.raises(TalkieConfigError, match="Ollama is not running"):
            check_connection("ollama")
