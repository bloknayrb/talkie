"""Configuration management with default merging and keyring support."""

import json
from typing import Any, Optional

import keyring

from talkie_modules.paths import CONFIG_FILE
from talkie_modules.logger import get_logger

logger = get_logger("config")

_KEYRING_SERVICE = "Talkie"
_KEY_NAMES = ("openai_key", "groq_key", "anthropic_key")

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


def _get_key_from_keyring(key_name: str) -> str:
    """Retrieve an API key from Windows Credential Manager."""
    try:
        val = keyring.get_password(_KEYRING_SERVICE, key_name)
        return val or ""
    except Exception as e:
        logger.debug("Keyring read failed for %s: %s", key_name, e)
        return ""


def _set_key_in_keyring(key_name: str, value: str) -> bool:
    """Store an API key in Windows Credential Manager. Returns True on success."""
    try:
        if value:
            keyring.set_password(_KEYRING_SERVICE, key_name, value)
        else:
            try:
                keyring.delete_password(_KEYRING_SERVICE, key_name)
            except keyring.errors.PasswordDeleteError:
                pass
        return True
    except Exception as e:
        logger.warning("Keyring write failed for %s: %s", key_name, e)
        return False


def _migrate_keys_to_keyring(config: dict[str, Any]) -> bool:
    """Move plaintext keys from config.json to keyring. Returns True if any migrated."""
    migrated = False
    for key_name in _KEY_NAMES:
        plaintext_key = config.get(key_name, "")
        if plaintext_key and not plaintext_key.startswith("keyring:"):
            if _set_key_in_keyring(key_name, plaintext_key):
                config[key_name] = ""  # Clear from config
                logger.info("Migrated %s to keyring", key_name)
                migrated = True
    return migrated


def load_config() -> dict[str, Any]:
    """Load config from disk, merging with defaults. API keys come from keyring."""
    config: dict[str, Any] = dict(DEFAULT_CONFIG)

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        config.update(user_config)
        # Deep merge for nested dicts
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

    # Migrate any plaintext keys to keyring on first run
    if _migrate_keys_to_keyring(config):
        save_config(config)

    # Load keys from keyring (overrides empty config values)
    for key_name in _KEY_NAMES:
        keyring_val = _get_key_from_keyring(key_name)
        if keyring_val:
            config[key_name] = keyring_val

    return config


def save_config(config: dict[str, Any]) -> None:
    """Write config dict to disk. API keys should NOT be in config — they go to keyring."""
    # Make a copy to avoid mutating the original
    config_to_save = dict(config)
    # Strip keys from file — they live in keyring
    for key_name in _KEY_NAMES:
        config_to_save[key_name] = ""

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_to_save, f, indent=4)
    logger.debug("Config saved to %s", CONFIG_FILE)


def save_api_key(key_name: str, value: str) -> bool:
    """Store a single API key in keyring. Returns True on success."""
    if key_name not in _KEY_NAMES:
        logger.warning("Unknown key name: %s", key_name)
        return False
    return _set_key_in_keyring(key_name, value)


def get_api_key(key_name: str) -> str:
    """Retrieve a single API key from keyring."""
    return _get_key_from_keyring(key_name)


def validate_api_key_format(key_name: str, value: str) -> Optional[str]:
    """
    Quick format validation for API keys.
    Returns None if valid, or an error message string.
    """
    if not value:
        return "Key is empty"

    if key_name == "openai_key":
        if not (value.startswith("sk-") and len(value) >= 20):
            return "OpenAI keys start with 'sk-' and are 20+ characters"
    elif key_name == "groq_key":
        if not (value.startswith("gsk_") and len(value) >= 20):
            return "Groq keys start with 'gsk_' and are 20+ characters"
    elif key_name == "anthropic_key":
        if not (value.startswith("sk-ant-") and len(value) >= 20):
            return "Anthropic keys start with 'sk-ant-' and are 20+ characters"

    return None
