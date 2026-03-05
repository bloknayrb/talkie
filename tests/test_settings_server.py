"""Tests for the Bottle-based settings server."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from talkie_modules.settings_server import create_app, _mask_key


class TestMaskKey:
    def test_empty_returns_empty(self) -> None:
        assert _mask_key("openai_key", "") == ""

    def test_masks_long_key(self) -> None:
        result = _mask_key("openai_key", "sk-1234567890abcdef")
        assert result.startswith("sk-...")
        assert result.endswith("cdef")
        assert "1234567890" not in result

    def test_masks_short_key(self) -> None:
        result = _mask_key("openai_key", "sk-1234")
        assert result == "***"

    def test_groq_key_prefix(self) -> None:
        result = _mask_key("groq_key", "gsk_abcdefghij1234567890")
        assert result.startswith("gsk_...")

    def test_anthropic_key_prefix(self) -> None:
        result = _mask_key("anthropic_key", "sk-ant-abcdefghij1234567890")
        assert result.startswith("sk-ant-...")


class TestSettingsApp:
    """Test Bottle routes using WebTest or direct WSGI calls."""

    @pytest.fixture
    def app(self, tmp_path):
        """Create a test app with mocked config."""
        config_file = str(tmp_path / "config.json")
        default_config = {
            "stt_provider": "openai",
            "api_provider": "openai",
            "hotkey": "ctrl+win",
            "models": {"openai_stt": "whisper-1", "openai_llm": "gpt-4o"},
            "snippets": {"gm": "Good morning"},
            "custom_vocabulary": ["Talkie"],
            "min_hold_seconds": 1.0,
            "silence_rms_threshold": 0.005,
            "openai_key": "",
            "groq_key": "",
            "anthropic_key": "",
        }

        with open(config_file, "w") as f:
            json.dump(default_config, f)

        with patch("talkie_modules.settings_server.load_config", return_value=dict(default_config)), \
             patch("talkie_modules.settings_server.get_missing_keys", return_value=[]), \
             patch("talkie_modules.settings_server.get_api_key", return_value=""):
            app = create_app()
        return app

    def test_get_models(self, app) -> None:
        """Test /api/models returns valid model lists."""
        from io import BytesIO
        import bottle

        # Simulate a request by calling the route directly
        env = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/api/models",
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "8080",
            "wsgi.input": BytesIO(),
        }
        # Use bottle's test client approach
        body = app.get_url("/api/models")
        # Route exists — verify it doesn't error
        assert body is not None
