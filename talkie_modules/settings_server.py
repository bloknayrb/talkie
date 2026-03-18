"""Bottle-based settings server for Talkie web UI.

Runs on a daemon thread, serving the settings SPA and handling config API calls.
Binds to 127.0.0.1:0 (OS-assigned port) to avoid conflicts.
"""

import os
import threading
import uuid
from typing import Any, Optional

import bottle

from talkie_modules.config_manager import (
    DEFAULT_CONFIG,
    load_config,
    save_config,
    save_api_key,
    get_api_key,
    validate_api_key_format,
    get_missing_keys,
)
from talkie_modules.logger import get_logger
from talkie_modules.providers import (
    PROVIDERS,
    KEY_NAMES,
    KEY_PREFIXES,
    STT_MODELS,
    LLM_MODELS,
)
from talkie_modules.profile_templates import (
    PROFILE_TEMPLATES,
    get_template,
    apply_template_apps,
)

logger = get_logger("settings_server")

_VALID_PROVIDERS = frozenset(STT_MODELS) | frozenset(LLM_MODELS)
_VALID_STT_PROVIDERS = frozenset(STT_MODELS)
_VALID_LLM_PROVIDERS = frozenset(LLM_MODELS)

_NUMERIC_VALIDATORS = {
    "temperature": (float, 0.0, 2.0),
    "min_hold_seconds": (float, 0.2, 3.0),
    "silence_rms_threshold": (float, 0.001, 0.1),
}


def _validate_numeric(field: str, value: Any) -> Any:
    """Validate and coerce a numeric value against _NUMERIC_VALIDATORS. Aborts on error."""
    typ, lo, hi = _NUMERIC_VALIDATORS[field]
    try:
        val = typ(value)
    except (TypeError, ValueError):
        bottle.abort(400, f"{field} must be a number")
    if not (lo <= val <= hi):
        bottle.abort(400, f"{field} must be between {lo} and {hi}")
    return val


def _safe_error_message(error: Exception) -> str:
    """Extract a user-safe error description from API exceptions."""
    status = getattr(error, "status_code", None)
    if status == 401:
        return "Authentication failed — check your API key"
    if status == 403:
        return "Access denied — check your API key permissions"
    if status == 429:
        return "Rate limited — try again shortly"
    if status:
        return f"API error (HTTP {status})"
    if isinstance(error, (ConnectionError, TimeoutError)):
        return "Connection failed — check your network"
    return "Connection test failed"


def _mask_key(key_name: str, value: str) -> str:
    """Mask an API key for display. Returns 'sk-...xxxx' style."""
    if not value:
        return ""
    prefix = KEY_PREFIXES.get(key_name, "")
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

    def _require_valid_provider(provider):
        if provider not in _VALID_PROVIDERS:
            bottle.abort(400, f"Unknown provider: {provider!r}")

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
        for key_name in KEY_NAMES:
            config[key_name] = _mask_key(key_name, config.get(key_name, ""))
        # Add missing keys info for first-run detection
        config["_missing_keys"] = get_missing_keys(config)
        config["_default_system_prompt"] = DEFAULT_CONFIG["system_prompt"]
        return config

    @app.route("/api/config", method="POST")
    def post_config():
        try:
            data = bottle.request.json
            if not data:
                bottle.abort(400, "No JSON body")

            config = load_config()

            # Validate and update provider fields
            if "stt_provider" in data:
                if data["stt_provider"] not in _VALID_STT_PROVIDERS:
                    bottle.abort(400, f"Unknown STT provider: {data['stt_provider']!r}")
                config["stt_provider"] = data["stt_provider"]
            if "api_provider" in data:
                if data["api_provider"] not in _VALID_LLM_PROVIDERS:
                    bottle.abort(400, f"Unknown LLM provider: {data['api_provider']!r}")
                config["api_provider"] = data["api_provider"]

            # Validate and update numeric fields
            for field, (typ, lo, hi) in _NUMERIC_VALIDATORS.items():
                if field in data:
                    try:
                        val = typ(data[field])
                    except (TypeError, ValueError):
                        bottle.abort(400, f"{field} must be a number")
                    if not (lo <= val <= hi):
                        bottle.abort(400, f"{field} must be between {lo} and {hi}")
                    config[field] = val

            # Passthrough fields (no meaningful server-side constraints)
            for field in ("hotkey", "custom_vocabulary", "snippets",
                          "system_prompt", "log_level"):
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
        except bottle.HTTPError:
            raise
        except Exception as e:
            logger.error("Config save failed: %s", e)
            bottle.abort(500, "Failed to save configuration")

    # ---- API Keys ----

    @app.route("/api/keys/<provider>", method="GET")
    def get_key_status(provider):
        _require_valid_provider(provider)
        key_name = f"{provider}_key"
        value = get_api_key(key_name)
        return {"exists": bool(value), "masked": _mask_key(key_name, value)}

    @app.route("/api/keys/<provider>", method="POST")
    def save_key(provider):
        _require_valid_provider(provider)
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
        _require_valid_provider(provider)
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
            logger.warning("Connection test failed for %s: %s", provider, e)
            return {"status": "error", "message": _safe_error_message(e)}

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
        return {"stt": STT_MODELS, "llm": LLM_MODELS}

    # ---- Providers ----

    @app.route("/api/providers", method="GET")
    def get_providers():
        """Return provider metadata for dynamic frontend rendering."""
        result = []
        for pid, pinfo in PROVIDERS.items():
            result.append({
                "id": pid,
                "label": pinfo["label"],
                "placeholder": pinfo["key_prefix"] + "...",
                "url": pinfo["key_url"],
                "has_stt": pinfo["stt_models"] is not None,
                "has_llm": pinfo["llm_models"] is not None,
            })
        return {"providers": result}

    # ---- Profiles ----

    @app.route("/api/profiles", method="GET")
    def get_profiles():
        config = load_config()
        return {"profiles": config.get("profiles", [])}

    @app.route("/api/profiles", method="POST")
    def create_profile():
        data = bottle.request.json
        if not data:
            bottle.abort(400, "No JSON body")

        name = (data.get("name") or "").strip()
        if not name:
            bottle.abort(400, "Profile name is required")

        mp = (data.get("match_process") or "").strip()
        mt = (data.get("match_title") or "").strip()
        if not mp and not mt:
            bottle.abort(400, "At least one match field (process or title) is required")

        temp = data.get("temperature")
        if temp is not None:
            temp = _validate_numeric("temperature", temp)

        profile = {
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "match_process": mp,
            "match_title": mt,
            "system_prompt": data.get("system_prompt"),
            "snippets": data.get("snippets"),
            "custom_vocabulary": data.get("custom_vocabulary"),
            "temperature": temp,
        }

        config = load_config()
        profiles = config.get("profiles", [])
        profiles.append(profile)
        config["profiles"] = profiles
        save_config(config)

        if on_config_saved:
            on_config_saved()

        return {"status": "ok", "profile": profile}

    # Register reorder BEFORE the <id> route so "reorder" isn't captured as an id
    @app.route("/api/profiles/reorder", method="POST")
    def reorder_profiles():
        data = bottle.request.json
        if not data or "order" not in data:
            bottle.abort(400, "Missing 'order' field")

        order = data["order"]
        if not isinstance(order, list):
            bottle.abort(400, "'order' must be a list of profile IDs")

        config = load_config()
        profiles = config.get("profiles", [])
        by_id = {p["id"]: p for p in profiles}

        # Reorder: only include IDs that exist, append any missing at the end
        reordered = [by_id[pid] for pid in order if pid in by_id]
        order_set = set(order)
        remaining = [p for p in profiles if p["id"] not in order_set]
        config["profiles"] = reordered + remaining
        save_config(config)

        if on_config_saved:
            on_config_saved()

        return {"status": "ok"}

    @app.route("/api/profiles/<profile_id>", method="PUT")
    def update_profile(profile_id):
        data = bottle.request.json
        if not data:
            bottle.abort(400, "No JSON body")

        config = load_config()
        profiles = config.get("profiles", [])
        profile = next((p for p in profiles if p["id"] == profile_id), None)
        if not profile:
            bottle.abort(404, "Profile not found")

        if "name" in data:
            name = (data["name"] or "").strip()
            if not name:
                bottle.abort(400, "Profile name is required")
            profile["name"] = name

        if "match_process" in data or "match_title" in data:
            mp = (data.get("match_process", profile.get("match_process")) or "").strip()
            mt = (data.get("match_title", profile.get("match_title")) or "").strip()
            if not mp and not mt:
                bottle.abort(400, "At least one match field is required")
            profile["match_process"] = mp
            profile["match_title"] = mt

        if "temperature" in data:
            temp = data["temperature"]
            if temp is not None:
                temp = _validate_numeric("temperature", temp)
            profile["temperature"] = temp

        # Override fields that can be null (inherit) or a value
        for field in ("system_prompt", "snippets", "custom_vocabulary"):
            if field in data:
                profile[field] = data[field]

        config["profiles"] = profiles
        save_config(config)

        if on_config_saved:
            on_config_saved()

        return {"status": "ok", "profile": profile}

    @app.route("/api/profiles/<profile_id>", method="DELETE")
    def delete_profile(profile_id):
        config = load_config()
        profiles = config.get("profiles", [])
        config["profiles"] = [p for p in profiles if p["id"] != profile_id]
        save_config(config)

        if on_config_saved:
            on_config_saved()

        return {"status": "ok"}

    # ---- About ----

    @app.route("/api/about", method="GET")
    def about():
        version = get_version() if get_version else "unknown"
        return {"version": version}

    # ---- Profile Templates ----

    @app.route("/api/profile-templates", method="GET")
    def get_profile_templates():
        """Return template metadata for the picker UI."""
        return {"templates": [
            {
                "id": t["id"],
                "name": t["name"],
                "description": t["description"],
                "icon": t["icon"],
                "apps": [
                    {
                        "id": a["id"],
                        "name": a["name"],
                        "match_process": a["match_process"],
                        "match_title": a["match_title"],
                    }
                    for a in t["apps"]
                ],
            }
            for t in PROFILE_TEMPLATES
        ]}

    @app.route("/api/profile-templates/<template_id>/apply", method="POST")
    def apply_template(template_id):
        """Create profiles from a template for selected apps."""
        data = bottle.request.json
        if not data or "app_ids" not in data:
            bottle.abort(400, "Missing 'app_ids' field")

        app_ids = data["app_ids"]
        if not isinstance(app_ids, list):
            bottle.abort(400, "'app_ids' must be a list")

        template = get_template(template_id)
        if not template:
            bottle.abort(404, f"Template not found: {template_id}")

        config = load_config()
        profiles = config.get("profiles", [])

        result = apply_template_apps(template, app_ids, profiles)

        if result["created"]:
            profiles.extend(result["created"])
            config["profiles"] = profiles
            save_config(config)

            if on_config_saved:
                on_config_saved()

        return {
            "status": "ok",
            "created": result["created"],
            "skipped": result["skipped"],
        }

    @app.route("/api/profiles/<profile_id>/reset-template", method="POST")
    def reset_profile_template(profile_id):
        """Reset a profile to its template defaults."""
        config = load_config()
        profiles = config.get("profiles", [])
        profile = next((p for p in profiles if p["id"] == profile_id), None)
        if not profile:
            bottle.abort(404, "Profile not found")

        snapshot = profile.get("template_snapshot")
        if not snapshot:
            bottle.abort(400, "Profile has no template snapshot to reset from")

        for field in ("system_prompt", "snippets", "custom_vocabulary", "temperature"):
            if field in snapshot:
                profile[field] = snapshot[field]

        config["profiles"] = profiles
        save_config(config)

        if on_config_saved:
            on_config_saved()

        return {"status": "ok", "profile": profile}

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
