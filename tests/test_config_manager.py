"""Tests for config_manager."""

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from talkie_modules.config_manager import (
    DEFAULT_CONFIG,
    load_config,
    save_config,
    validate_api_key_format,
)


@pytest.fixture
def temp_config(tmp_path):
    """Create a temporary config file and patch CONFIG_FILE to point to it."""
    config_path = str(tmp_path / "config.json")
    with patch("talkie_modules.config_manager.CONFIG_FILE", config_path):
        yield config_path


class TestLoadConfig:
    def test_creates_default_when_missing(self, temp_config: str) -> None:
        config = load_config()
        assert config["hotkey"] == "ctrl+win"
        assert config["api_provider"] == "openai"
        assert config["min_hold_seconds"] == 1.0
        assert config["silence_rms_threshold"] == 0.005
        # File should have been created
        assert os.path.exists(temp_config)

    def test_merges_with_defaults(self, temp_config: str) -> None:
        # Write partial config
        with open(temp_config, "w") as f:
            json.dump({"hotkey": "ctrl+shift+r"}, f)

        config = load_config()
        # User value preserved
        assert config["hotkey"] == "ctrl+shift+r"
        # Default values filled in
        assert config["api_provider"] == "openai"
        assert "models" in config

    def test_deep_merges_models(self, temp_config: str) -> None:
        # Write config with partial models
        with open(temp_config, "w") as f:
            json.dump({"models": {"openai_llm": "gpt-4-turbo"}}, f)

        config = load_config()
        # User override
        assert config["models"]["openai_llm"] == "gpt-4-turbo"
        # Default preserved
        assert config["models"]["groq_llm"] == "llama-3.3-70b-versatile"

    def test_handles_invalid_json(self, temp_config: str) -> None:
        with open(temp_config, "w") as f:
            f.write("{invalid json")

        config = load_config()
        # Falls back to defaults
        assert config["hotkey"] == "ctrl+win"


class TestValidateApiKeyFormat:
    def test_empty_key(self) -> None:
        assert validate_api_key_format("openai_key", "") is not None

    def test_valid_openai(self) -> None:
        assert validate_api_key_format("openai_key", "sk-" + "a" * 40) is None

    def test_invalid_openai_prefix(self) -> None:
        assert validate_api_key_format("openai_key", "bad-" + "a" * 40) is not None

    def test_valid_groq(self) -> None:
        assert validate_api_key_format("groq_key", "gsk_" + "a" * 40) is None

    def test_invalid_groq_prefix(self) -> None:
        assert validate_api_key_format("groq_key", "sk-" + "a" * 40) is not None

    def test_valid_anthropic(self) -> None:
        assert validate_api_key_format("anthropic_key", "sk-ant-" + "a" * 40) is None

    def test_invalid_anthropic_prefix(self) -> None:
        assert validate_api_key_format("anthropic_key", "sk-" + "a" * 40) is not None

    def test_too_short(self) -> None:
        assert validate_api_key_format("openai_key", "sk-abc") is not None
