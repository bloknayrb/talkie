"""Bottle-based settings server for Talkie web UI.

Runs on a daemon thread, serving the settings SPA and handling config API calls.
Binds to 127.0.0.1:0 (OS-assigned port) to avoid conflicts.
"""

import copy
import os
import sys
import threading
import time
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
from talkie_modules.exceptions import TalkieConfigError
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

_ALLOWED_UPDATE_PREFIX = "https://github.com/bloknayrb/talkie/releases/"


def _provider_metadata_list() -> list[dict]:
    """Build provider metadata for frontend consumption. Used by multiple routes."""
    return [
        {
            "id": pid,
            "label": pinfo["label"],
            "requires_key": pinfo.get("requires_key", True),
            "placeholder": pinfo.get("key_prefix", "") + "..." if pinfo.get("requires_key", True) else "",
            "url": pinfo.get("key_url", ""),
            "has_stt": pinfo["stt_models"] is not None,
            "has_llm": pinfo["llm_models"] is not None,
        }
        for pid, pinfo in PROVIDERS.items()
    ]

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
    quit_app: Optional[callable] = None,
) -> bottle.Bottle:
    """
    Create the Bottle WSGI app with all routes.

    Args:
        on_config_saved: Callback when config is saved (e.g., to refresh hotkey)
        get_version: Callable returning version string
        quit_app: Callback to shut down the app (for update-and-restart)
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

        # Bundle data that the frontend needs at load time to avoid
        # multiple sequential round trips on a single-threaded server.
        config["_models"] = {"stt": STT_MODELS, "llm": LLM_MODELS}
        config["_providers"] = _provider_metadata_list()
        config["_key_statuses"] = {}
        for pid, pinfo in PROVIDERS.items():
            if pinfo.get("requires_key", True):
                key_name = f"{pid}_key"
                # Keys already loaded into config by load_config() — avoid re-reading keyring
                value = config.get(key_name, "")
                config["_key_statuses"][pid] = {
                    "exists": bool(value),
                    "masked": _mask_key(key_name, value),
                }
            else:
                config["_key_statuses"][pid] = {
                    "exists": True,
                    "masked": "",
                }
        config["_version"] = get_version() if get_version else "unknown"
        config["_is_frozen"] = getattr(sys, "frozen", False)

        from talkie_modules.audio_io import TONE_PRESETS
        config["_tone_presets"] = {
            k: {"label": v["label"], "description": v["description"]}
            for k, v in TONE_PRESETS.items()
        }

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
                          "system_prompt", "log_level", "notification_tone"):
                if field in data:
                    config[field] = data[field]

            if "start_on_boot" in data:
                config["start_on_boot"] = bool(data["start_on_boot"])

            # Update model selections
            if "models" in data:
                if "models" not in config:
                    config["models"] = {}
                config["models"].update(data["models"])

            save_config(config)

            if "start_on_boot" in data:
                from talkie_modules.autostart import sync_autostart
                sync_autostart(config.get("start_on_boot", False))

            if on_config_saved:
                on_config_saved()

            return {"status": "ok"}
        except bottle.HTTPError:
            raise
        except Exception as e:
            logger.error("Config save failed: %s", e)
            bottle.abort(500, "Failed to save configuration")

    # ---- API Keys ----

    def _require_keyed_provider(provider):
        """Reject providers that don't use API keys."""
        _require_valid_provider(provider)
        pinfo = PROVIDERS.get(provider, {})
        if not pinfo.get("requires_key", True):
            bottle.abort(400, f"Provider {provider!r} does not use API keys")

    @app.route("/api/keys/<provider>", method="GET")
    def get_key_status(provider):
        _require_keyed_provider(provider)
        key_name = f"{provider}_key"
        value = get_api_key(key_name)
        return {"exists": bool(value), "masked": _mask_key(key_name, value)}

    @app.route("/api/keys/<provider>", method="POST")
    def save_key(provider):
        _require_keyed_provider(provider)
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
        pinfo = PROVIDERS.get(provider, {})

        # Keyless providers skip key resolution
        if pinfo.get("requires_key", True):
            key_name = f"{provider}_key"
            api_key = data.get("key") or get_api_key(key_name)
            if not api_key:
                return {"status": "error", "message": "No API key provided"}
            err = validate_api_key_format(key_name, api_key)
            if err:
                return {"status": "error", "message": err}
        else:
            api_key = ""

        try:
            from talkie_modules.api_client import test_connection as _test
            _test(provider, api_key)
            return {"status": "ok", "message": f"{pinfo.get('label', provider)}: connected"}
        except Exception as e:
            logger.warning("Connection test failed for %s: %s", provider, e)
            msg = str(e) if isinstance(e, (TalkieConfigError,)) else _safe_error_message(e)
            return {"status": "error", "message": msg}

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
        return {"providers": _provider_metadata_list()}

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

    # ---- Updates ----

    _update_state = {"downloading": False, "progress": 0, "error": None, "ready": False}
    _update_lock = threading.Lock()
    _DEV_MODE_MSG = "Updates only work in the packaged exe."

    def _is_dev_mode():
        return not getattr(sys, "frozen", False)

    @app.route("/api/update/check", method="GET")
    def check_update():
        if _is_dev_mode():
            version = get_version() if get_version else "unknown"
            return {"available": False, "current_version": version,
                    "error": _DEV_MODE_MSG}
        from talkie_modules.updater import check_for_update
        version = get_version() if get_version else "0.0.0"
        result = check_for_update(version)
        result["current_version"] = version
        return result

    @app.route("/api/update/download", method="POST")
    def start_download():
        if _is_dev_mode():
            return {"status": "error", "error": _DEV_MODE_MSG}

        with _update_lock:
            if _update_state["downloading"]:
                return {"status": "already_downloading"}
            _update_state["downloading"] = True
            _update_state["progress"] = 0
            _update_state["error"] = None
            _update_state["ready"] = False

        data = bottle.request.json or {}
        url = data.get("url", "")
        expected_size = data.get("expected_size", 0)

        # Validate URL is from the expected GitHub repo
        if not url or not url.startswith(_ALLOWED_UPDATE_PREFIX):
            with _update_lock:
                _update_state["downloading"] = False
                _update_state["error"] = "Invalid download URL"
            return {"status": "error", "error": "Invalid download URL"}

        from talkie_modules.paths import BASE_DIR
        dest = os.path.join(BASE_DIR, "Talkie_update.exe")

        def _download():
            from talkie_modules.updater import download_update
            _last_pct = [-1]  # mutable container for closure

            def _progress(downloaded, total):
                pct = round((downloaded / total * 100) if total else 0, 1)
                if pct == _last_pct[0]:
                    return  # skip redundant lock acquisition
                _last_pct[0] = pct
                with _update_lock:
                    _update_state["progress"] = pct

            try:
                download_update(url, dest, expected_size, _progress)
                with _update_lock:
                    _update_state["downloading"] = False
                    _update_state["ready"] = True
            except PermissionError:
                with _update_lock:
                    _update_state["downloading"] = False
                    _update_state["error"] = "Permission denied — can't write to the app directory."
            except Exception as exc:
                logger.error("Update download failed: %s", exc)
                with _update_lock:
                    _update_state["downloading"] = False
                    _update_state["error"] = str(exc)

        threading.Thread(target=_download, daemon=True).start()
        return {"status": "downloading"}

    @app.route("/api/update/download", method="GET")
    def poll_download():
        with _update_lock:
            return dict(_update_state)

    @app.route("/api/update/apply", method="POST")
    def apply_update_route():
        if _is_dev_mode():
            return {"status": "error", "error": _DEV_MODE_MSG}

        with _update_lock:
            if not _update_state["ready"]:
                return {"status": "error", "error": "No completed download to apply."}
            _update_state["ready"] = False  # prevent double-apply

        from talkie_modules.paths import BASE_DIR
        from talkie_modules.updater import apply_update
        update_path = os.path.join(BASE_DIR, "Talkie_update.exe")
        if not os.path.exists(update_path):
            return {"status": "error", "error": "No update file found."}

        apply_update(sys.executable, update_path)

        # Schedule shutdown after a short delay so the HTTP response returns.
        # Failsafe os._exit ensures the process dies even if quit_app blocks
        # (e.g. tray_icon.stop() hanging).
        threading.Timer(3.0, lambda: os._exit(0)).start()
        if quit_app:
            threading.Timer(0.5, quit_app).start()

        return {"status": "ok"}

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
                profile[field] = copy.deepcopy(snapshot[field])

        config["profiles"] = profiles
        save_config(config)

        if on_config_saved:
            on_config_saved()

        return {"status": "ok", "profile": profile}

    # ---- History ----

    @app.route("/api/history", method="GET")
    def get_history():
        from talkie_modules.history import get_entries
        limit = bottle.request.params.get("limit")
        limit = int(limit) if limit and limit.isdigit() else None
        return {"entries": get_entries(limit)}

    @app.route("/api/history", method="DELETE")
    def clear_history():
        from talkie_modules.history import clear
        clear()
        return {"status": "ok"}

    @app.route("/api/history/<entry_id>", method="DELETE")
    def delete_history_entry(entry_id):
        from talkie_modules.history import delete_entry
        if delete_entry(entry_id):
            return {"status": "ok"}
        bottle.abort(404, "Entry not found")

    # ---- Audio / Tone Preview ----

    @app.route("/api/audio/preview-tone", method="POST")
    def preview_tone():
        import tempfile
        import sounddevice as sd
        import soundfile as sf_lib
        from talkie_modules.audio_io import TONE_PRESETS, _generate_tone
        data = bottle.request.json
        if not data or "tone" not in data:
            bottle.abort(400, "Missing 'tone' field")
        tone = data["tone"]
        if tone not in TONE_PRESETS:
            bottle.abort(400, f"Unknown tone preset: {tone}")

        preset = TONE_PRESETS[tone]
        if preset["start"] is None:
            return {"status": "ok"}

        # Generate temp WAVs, play them, clean up — no preset state mutation
        tmp_dir = tempfile.mkdtemp()
        try:
            start_path = os.path.join(tmp_dir, "start.wav")
            stop_path = os.path.join(tmp_dir, "stop.wav")
            if preset["start"]:
                _generate_tone(start_path, preset["start"])
                data_s, fs = sf_lib.read(start_path)
                sd.play(data_s, fs)
                sd.wait()
            time.sleep(1.0)
            if preset["stop"]:
                _generate_tone(stop_path, preset["stop"])
                data_t, fs = sf_lib.read(stop_path)
                sd.play(data_t, fs)
                sd.wait()
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return {"status": "ok"}

    # ---- Local Whisper ----

    _whisper_dl_state = {
        "downloading": False, "target": "", "progress": 0, "error": None,
    }
    _whisper_dl_lock = threading.Lock()

    @app.route("/api/local/whisper/status", method="GET")
    def whisper_status():
        from talkie_modules.local_whisper import (
            is_binary_available, get_downloaded_models, MODEL_SIZES_MB,
        )
        with _whisper_dl_lock:
            dl = dict(_whisper_dl_state)
        return {
            "binary_installed": is_binary_available(),
            "downloaded_models": get_downloaded_models(),
            "model_sizes_mb": MODEL_SIZES_MB,
            "download": dl,
        }

    def _start_whisper_download(target_label, download_fn):
        """Shared helper: start a background whisper download with progress tracking."""
        with _whisper_dl_lock:
            if _whisper_dl_state["downloading"]:
                return {"status": "already_downloading"}
            _whisper_dl_state.update(
                downloading=True, target=target_label, progress=0, error=None,
            )

        def _do_download():
            try:
                def _progress(downloaded, total):
                    pct = round((downloaded / total * 100) if total else 0, 1)
                    with _whisper_dl_lock:
                        _whisper_dl_state["progress"] = pct
                download_fn(_progress)
                with _whisper_dl_lock:
                    _whisper_dl_state["downloading"] = False
                    _whisper_dl_state["progress"] = 100
            except Exception as exc:
                logger.error("Whisper download failed (%s): %s", target_label, exc)
                with _whisper_dl_lock:
                    _whisper_dl_state["downloading"] = False
                    _whisper_dl_state["error"] = str(exc)

        threading.Thread(target=_do_download, daemon=True).start()
        return {"status": "downloading"}

    @app.route("/api/local/whisper/download-binary", method="POST")
    def whisper_download_binary():
        from talkie_modules.local_whisper import download_binary, is_binary_available
        if is_binary_available():
            return {"status": "ok", "message": "Already installed"}
        return _start_whisper_download("binary", download_binary)

    @app.route("/api/local/whisper/download-model", method="POST")
    def whisper_download_model():
        from talkie_modules.local_whisper import download_model, VALID_MODELS
        data = bottle.request.json
        if not data or "model" not in data:
            bottle.abort(400, "Missing 'model' field")
        model_name = data["model"]
        if model_name not in VALID_MODELS:
            bottle.abort(400, f"Unknown model: {model_name}")
        return _start_whisper_download(
            model_name, lambda cb: download_model(model_name, cb),
        )

    @app.route("/api/local/whisper/download", method="GET")
    def whisper_download_poll():
        with _whisper_dl_lock:
            return dict(_whisper_dl_state)

    # ---- Ollama ----

    @app.route("/api/local/ollama/models", method="GET")
    def ollama_models():
        from talkie_modules.ollama_utils import list_models
        models = list_models()
        if models is None:
            return {"status": "not_running", "models": []}
        return {"status": "ok", "models": models}

    return app


class SettingsServer:
    """Manages the Bottle server lifecycle on a daemon thread."""

    def __init__(
        self,
        on_config_saved: Optional[callable] = None,
        get_version: Optional[callable] = None,
        quit_app: Optional[callable] = None,
    ) -> None:
        self._app = create_app(on_config_saved, get_version, quit_app)
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
