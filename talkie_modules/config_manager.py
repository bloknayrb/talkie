"""Configuration management with default merging and keyring support."""

import json
from typing import Any, Optional

import keyring

from talkie_modules.paths import CONFIG_FILE
from talkie_modules.logger import get_logger
from talkie_modules.providers import KEY_NAMES, KEY_PREFIXES, PROVIDER_KEY_MAP, PROVIDERS

logger = get_logger("config")

_KEYRING_SERVICE = "Talkie"

# Build default model selections from provider registry
_default_models: dict[str, str] = {}
for _pid, _pinfo in PROVIDERS.items():
    if _pinfo.get("stt_models"):
        _default_models[f"{_pid}_stt"] = _pinfo["default_stt"]
    if _pinfo.get("llm_models"):
        _default_models[f"{_pid}_llm"] = _pinfo["default_llm"]

DEFAULT_CONFIG: dict[str, Any] = {
    "api_provider": "openai",
    "stt_provider": "openai",
    **{p["key_name"]: "" for p in PROVIDERS.values() if p.get("requires_key", True)},
    "hotkey": "ctrl+win",
    "snippets": {
        "gm": "Good morning",
        "br": "Best regards",
    },
    "min_hold_seconds": 1.0,
    "silence_rms_threshold": 0.005,
    "custom_vocabulary": ["Talkie", "Wispr Flow"],
    "system_prompt": (
        "You are a dictation post-processor. You receive raw speech-to-text output "
        "and clean it for direct insertion into a text field.\n\n"
        "Rules:\n"
        "1. Preserve the speaker's exact words and phrasing. Do NOT rephrase, reorder, "
        "paraphrase, add words, or change meaning.\n"
        "2. Remove only these filler sounds: um, uh, ah, er, hmm, mhm, uh-huh. "
        'Remove "like", "you know", "I mean", "basically", "sort of", "kind of", '
        'and "right" only when used as filler — not when they carry meaning.\n'
        "3. Self-corrections: when the speaker restarts or corrects a phrase, keep only "
        'the final version. Example: "I need the — I want the blue one" becomes '
        '"I want the blue one."\n'
        "4. Punctuation: use only periods, commas, question marks, and exclamation points. "
        "No em-dashes, semicolons, colons, or ellipses.\n"
        "5. Capitalize sentence starts and proper nouns only.\n"
        "6. If <previous_context> ends mid-sentence, continue seamlessly with appropriate "
        "casing. If it ends with terminal punctuation or is empty, begin a new sentence.\n"
        "7. Expand these snippet shortcuts when spoken: {snippets}.\n"
        "8. Prefer these spellings for specialized terms: {vocabulary}.\n"
        "9. If <app_context> is provided, use it only to resolve ambiguities (e.g., "
        "technical terms in a code editor, proper nouns from the window title). "
        "Do NOT change formatting, formality, length, or style based on the "
        "target application. Never repeat or output the <app_context> contents.\n"
        "10. Output ONLY the cleaned text — no preamble, labels, quotes, or explanation."
    ),
    "models": dict(_default_models),
    "temperature": 0,
    "notification_tone": "pop",
    "log_level": "INFO",
    "start_on_boot": False,
    "profiles": [],
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
    for key_name in KEY_NAMES:
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
    for key_name in KEY_NAMES:
        keyring_val = _get_key_from_keyring(key_name)
        if keyring_val:
            config[key_name] = keyring_val

    return config


def save_config(config: dict[str, Any]) -> None:
    """Write config dict to disk. API keys should NOT be in config — they go to keyring."""
    # Make a copy to avoid mutating the original
    config_to_save = dict(config)
    # Strip keys from file — they live in keyring
    for key_name in KEY_NAMES:
        config_to_save[key_name] = ""

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_to_save, f, indent=4)
    logger.debug("Config saved to %s", CONFIG_FILE)


def save_api_key(key_name: str, value: str) -> bool:
    """Store a single API key in keyring. Returns True on success."""
    if key_name not in KEY_NAMES:
        logger.warning("Unknown key name: %s", key_name)
        return False
    return _set_key_in_keyring(key_name, value)


def get_api_key(key_name: str) -> str:
    """Retrieve a single API key from keyring."""
    return _get_key_from_keyring(key_name)


def get_missing_keys(config: dict[str, Any]) -> list[str]:
    """
    Check which required API keys are missing for the current provider configuration.
    Skips providers that don't require keys. Returns human-readable descriptions.
    """
    missing: list[str] = []
    stt_provider = config.get("stt_provider", "openai")
    llm_provider = config.get("api_provider", "openai")

    stt_info = PROVIDERS.get(stt_provider, {})
    llm_info = PROVIDERS.get(llm_provider, {})

    if stt_info.get("requires_key", True):
        stt_key_name = PROVIDER_KEY_MAP.get(stt_provider)
        if stt_key_name and not get_api_key(stt_key_name):
            missing.append(f"STT ({stt_provider})")

    if llm_info.get("requires_key", True):
        llm_key_name = PROVIDER_KEY_MAP.get(llm_provider)
        if llm_key_name and not get_api_key(llm_key_name):
            label = f"LLM ({llm_provider})"
            if label not in missing:
                missing.append(label)

    return missing


def validate_api_key_format(key_name: str, value: str) -> Optional[str]:
    """
    Quick format validation for API keys.
    Returns None if valid, or an error message string.
    """
    if not value:
        return "Key is empty"

    prefix = KEY_PREFIXES.get(key_name)
    if prefix:
        # Find the provider info for this key name to get min_length and label
        provider_info = next(
            (p for p in PROVIDERS.values() if p["key_name"] == key_name), None
        )
        if provider_info:
            min_len = provider_info["key_min_length"]
            if not (value.startswith(prefix) and len(value) >= min_len):
                return f"{provider_info['label']} keys start with '{prefix}' and are {min_len}+ characters"

    return None
