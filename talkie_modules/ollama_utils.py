"""Ollama utilities — reachability check and model discovery."""

import json
import urllib.error
import urllib.request
from typing import Optional

from talkie_modules.logger import get_logger
from talkie_modules.providers import PROVIDERS

logger = get_logger("ollama")

# Derive from registry — strip the /v1 OpenAI-compat suffix to get the native API base
_OLLAMA_BASE = PROVIDERS["ollama"]["base_url"].rsplit("/v1", 1)[0]
_TIMEOUT = 2  # seconds — keep fast so the UI doesn't hang


def is_running() -> bool:
    """Check if Ollama is reachable at localhost:11434."""
    try:
        req = urllib.request.Request(
            f"{_OLLAMA_BASE}/api/tags",
            headers={"User-Agent": "Talkie"},
        )
        urllib.request.urlopen(req, timeout=_TIMEOUT)
        return True
    except (urllib.error.URLError, OSError):
        return False


def list_models() -> Optional[list[str]]:
    """Query Ollama for installed models. Returns None if unreachable."""
    try:
        req = urllib.request.Request(
            f"{_OLLAMA_BASE}/api/tags",
            headers={"User-Agent": "Talkie"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError):
        return None

    try:
        models = data.get("models", [])
        return [m["name"].removesuffix(":latest") for m in models]
    except (KeyError, TypeError) as e:
        logger.warning("Failed to parse Ollama model list: %s", e)
        return []
