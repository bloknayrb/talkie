"""Bottle-based settings server for Talkie web UI.

Runs on a daemon thread, serving the settings SPA and handling config API calls.
Binds to 127.0.0.1:0 (OS-assigned port) to avoid conflicts.
"""

import json
import os
import threading
from typing import Any, Optional

import bottle

from talkie_modules.config_manager import (
    load_config,
    save_config,
    save_api_key,
    get_api_key,
    validate_api_key_format,
    get_missing_keys,
)
from talkie_modules.logger import get_logger

logger = get_logger("settings_server")

# Static model lists per provider
_STT_MODELS: dict[str, list[str]] = {
    "openai": ["whisper-1"],
    "groq": ["whisper-large-v3-turbo", "whisper-large-v3"],
}

_LLM_MODELS: dict[str, list[str]] = {
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
    "anthropic": ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"],
}

# Key name to human-friendly prefix mapping for masking
_KEY_PREFIXES = {
    "openai_key": "sk-",
    "groq_key": "gsk_",
    "anthropic_key": "sk-ant-",
}

_KEY_NAMES = ("openai_key", "groq_key", "anthropic_key")


def _mask_key(key_name: str, value: str) -> str:
    """Mask an API key for display. Returns 'sk-...xxxx' style."""
    if not value:
        return ""
    prefix = _KEY_PREFIXES.get(key_name, "")
    if len(value) > 8:
        return f"{prefix}...{value[-4:]}"
    return "***"


def create_app(
    on_config_saved: Optional[callable] = None,
    get_version: Optional[callable] = None,
) -> bottle.Bottle:
    """
    Create the Bottle WSGI app with all routes.

    Args:
        on_config_saved: Callback when config is saved (e.g., to refresh hotkey)
        get_version: Callable returning version string
    """
    app = bottle.Bottle()

    # Directory containing web_ui assets
    web_ui_dir = os.path.join(os.path.dirname(__file__), "web_ui")

    # ---- HTML ----

    @app.route("/")
    def index():
        return bottle.static_file("settings.html", root=web_ui_dir)

    @app.route("/static/<filepath:path>")
    def static(filepath):
        return bottle.static_file(filepath, root=web_ui_dir)

    # ---- Config API ----

    @app.route("/api/config", method="GET")
    def get_config():
        config = load_config()
        # Mask API keys
        for key_name in _KEY_NAMES:
            config[key_name] = _mask_key(key_name, config.get(key_name, ""))
        # Add missing keys info for first-run detection
        config["_missing_keys"] = get_missing_keys(config)
        return config

    @app.route("/api/config", method="POST")
    def post_config():
        try:
            data = bottle.request.json
            if not data:
                bottle.abort(400, "No JSON body")

            config = load_config()

            # Update simple fields
            for field in ("stt_provider", "api_provider", "hotkey",
                          "min_hold_seconds", "silence_rms_threshold",
                          "custom_vocabulary", "snippets", "system_prompt",
                          "temperature", "log_level"):
                if field in data:
                    config[field] = data[field]

            # Update model selections
            if "models" in data:
                if "models" not in config:
                    config["models"] = {}
                config["models"].update(data["models"])

            save_config(config)

            if on_config_saved:
                on_config_saved()

            return {"status": "ok"}
        except Exception as e:
            logger.error("Config save failed: %s", e)
            bottle.abort(500, str(e))

    # ---- API Keys ----

    @app.route("/api/keys/<provider>", method="GET")
    def get_key_status(provider):
        key_name = f"{provider}_key"
        value = get_api_key(key_name)
        return {"exists": bool(value), "masked": _mask_key(key_name, value)}

    @app.route("/api/keys/<provider>", method="POST")
    def save_key(provider):
        key_name = f"{provider}_key"
        data = bottle.request.json
        if not data or "key" not in data:
            bottle.abort(400, "Missing 'key' field")

        key_value = data["key"]

        # Validate format
        err = validate_api_key_format(key_name, key_value)
        if err:
            return {"status": "error", "message": err}

        success = save_api_key(key_name, key_value)
        if success:
            return {"status": "ok", "masked": _mask_key(key_name, key_value)}
        else:
            return {"status": "error", "message": "Failed to save to keyring"}

    # ---- Test Connection ----

    @app.route("/api/test-connection", method="POST")
    def test_connection():
        data = bottle.request.json
        if not data:
            bottle.abort(400, "No JSON body")

        provider = data.get("provider", "")
        key_name = f"{provider}_key"
        api_key = data.get("key") or get_api_key(key_name)

        if not api_key:
            return {"status": "error", "message": "No API key provided"}

        err = validate_api_key_format(key_name, api_key)
        if err:
            return {"status": "error", "message": err}

        try:
            from talkie_modules.api_client import test_connection as _test
            _test(provider, api_key)
            return {"status": "ok", "message": f"{provider}: connected"}
        except Exception as e:
            return {"status": "error", "message": str(e)[:100]}

    # ---- Hotkey Recording ----
    # Uses polling: POST starts recording, GET checks result

    _hotkey_result: dict[str, Any] = {"recording": False, "result": None}
    _hotkey_lock = threading.Lock()

    @app.route("/api/record-hotkey", method="POST")
    def start_hotkey_record():
        with _hotkey_lock:
            if _hotkey_result["recording"]:
                return {"status": "already_recording"}
            _hotkey_result["recording"] = True
            _hotkey_result["result"] = None

        def _record():
            try:
                import keyboard
                hotkey = keyboard.read_hotkey(suppress=False)
                with _hotkey_lock:
                    _hotkey_result["result"] = hotkey
                    _hotkey_result["recording"] = False
            except Exception as e:
                logger.warning("Hotkey recording failed: %s", e)
                with _hotkey_lock:
                    _hotkey_result["result"] = None
                    _hotkey_result["recording"] = False

        threading.Thread(target=_record, daemon=True).start()
        return {"status": "recording"}

    @app.route("/api/record-hotkey", method="GET")
    def poll_hotkey():
        with _hotkey_lock:
            return {
                "recording": _hotkey_result["recording"],
                "result": _hotkey_result["result"],
            }

    # ---- Models ----

    @app.route("/api/models", method="GET")
    def get_models():
        return {"stt": _STT_MODELS, "llm": _LLM_MODELS}

    # ---- About ----

    @app.route("/api/about", method="GET")
    def about():
        version = get_version() if get_version else "unknown"
        return {"version": version}

    return app


class SettingsServer:
    """Manages the Bottle server lifecycle on a daemon thread."""

    def __init__(
        self,
        on_config_saved: Optional[callable] = None,
        get_version: Optional[callable] = None,
    ) -> None:
        self._app = create_app(on_config_saved, get_version)
        self._server: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None
        self.port: int = 0

    def start(self) -> int:
        """Start the server. Returns the assigned port."""
        import socket

        # Find a free port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]

        def _run():
            try:
                bottle.run(
                    self._app,
                    host="127.0.0.1",
                    port=self.port,
                    quiet=True,
                    server="wsgiref",
                )
            except Exception as e:
                logger.error("Settings server error: %s", e)

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

        logger.info("Settings server started on port %d", self.port)
        return self.port

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        """Stop the server (best-effort, daemon thread will die with process)."""
        # wsgiref doesn't have a clean shutdown, but as a daemon thread it'll
        # be killed when the process exits
        logger.info("Settings server stopping")
