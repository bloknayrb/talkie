"""Configuration management with default merging."""

import json
from typing import Any

from talkie_modules.paths import CONFIG_FILE
from talkie_modules.logger import get_logger

logger = get_logger("config")

DEFAULT_CONFIG: dict[str, Any] = {
    "api_provider": "openai",
    "stt_provider": "openai",
    "openai_key": "",
    "groq_key": "",
    "anthropic_key": "",
    "hotkey": "alt+space",
    "snippets": {
        "gm": "Good morning",
        "br": "Best regards",
    },
    "custom_vocabulary": ["Talkie", "Wispr Flow"],
    "system_prompt": (
        "You are an expert transcriber. Transcribe the following audio based on the "
        "provided <previous_context>. If the context ends mid-sentence, continue it "
        "logically with appropriate capitalization and spacing. If context ends with a "
        "period, start the next sentence with an uppercase letter. Remove filler words, "
        "self-corrections, and apply custom vocabulary spellings. Expand the following "
        "snippets: {snippets}. Output ONLY the final processed text."
    ),
    "models": {
        "openai_stt": "whisper-1",
        "groq_stt": "whisper-large-v3-turbo",
        "openai_llm": "gpt-4o",
        "groq_llm": "llama-3.3-70b-versatile",
        "anthropic_llm": "claude-sonnet-4-20250514",
    },
    "log_level": "INFO",
}


def load_config() -> dict[str, Any]:
    """Load config from disk, merging with defaults so no keys are missing."""
    config: dict[str, Any] = dict(DEFAULT_CONFIG)

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        # Shallow merge — user values override defaults
        config.update(user_config)
        # Deep merge for nested dicts (models, snippets)
        for key in ("models", "snippets"):
            if key in DEFAULT_CONFIG and key in user_config:
                merged = dict(DEFAULT_CONFIG[key])
                merged.update(user_config[key])
                config[key] = merged
        logger.debug("Config loaded from %s", CONFIG_FILE)
    except FileNotFoundError:
        logger.info("No config file found, creating defaults at %s", CONFIG_FILE)
        save_config(config)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in config file: %s — using defaults", e)

    return config


def save_config(config: dict[str, Any]) -> None:
    """Write config dict to disk."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
    logger.debug("Config saved to %s", CONFIG_FILE)
