"""Talkie — hold-to-talk voice dictation app."""

import ctypes
import logging
import os
import sys
import threading
import time
from typing import Optional

from dotenv import load_dotenv

from talkie_modules.logger import setup_logging, get_logger
from talkie_modules.config_manager import load_config, save_config, get_missing_keys
from talkie_modules.audio_io import ensure_assets, set_tone_preset, start_recording, stop_recording, play_stop_chime, compute_rms
from talkie_modules.hotkey_manager import HotkeyManager
from talkie_modules.context_capture import get_context, get_target_window
from talkie_modules.profile_matcher import resolve_profile, apply_profile
from talkie_modules.api_client import transcribe_audio, process_text_llm
from talkie_modules.text_injector import inject_text, is_terminal_process
from talkie_modules.settings_server import SettingsServer
from talkie_modules.status_indicator_native import NativeStatusIndicator
from talkie_modules.state import StateMachine, AppState
from talkie_modules.notifications import notify_error, notify_discard
from talkie_modules.exceptions import TalkieError
from talkie_modules.paths import LOG_FILE, BASE_DIR

logger = get_logger("app")

__version__ = "1.6.8"

# ---------------------------------------------------------------------------
# Single-instance guard
# ---------------------------------------------------------------------------

_MUTEX_NAME = "Global\\TalkieSingleInstance"
_mutex_handle = None


def _acquire_single_instance() -> bool:
    """Acquire a named mutex to prevent multiple instances. Returns True if acquired."""
    global _mutex_handle
    _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, True, _MUTEX_NAME)
    last_error = ctypes.windll.kernel32.GetLastError()
    if last_error == 183:  # ERROR_ALREADY_EXISTS
        logger.warning("Another Talkie instance is already running.")
        return False
    return True


class TalkieApp:
    def __init__(self) -> None:
        self.config = load_config()

        # Initialize logging from config
        setup_logging(self._log_level())

        ensure_assets(self.config.get("notification_tone", "pop"))
        self.hotkey_manager: Optional[HotkeyManager] = None
        self.tray_icon = None
        self.state: StateMachine = StateMachine()
        self._indicator: Optional[NativeStatusIndicator] = None
        self._settings_server: Optional[SettingsServer] = None
        self._pending_hwnd: int = 0
        self._pending_process: str = ""
        self._pending_title: str = ""
        self._press_time: float = 0.0
        self._last_injected: str = ""

    def _log_level(self) -> int:
        return getattr(logging, self.config.get("log_level", "INFO").upper(), logging.INFO)

    def _strip_prior_injection(self, context: str) -> str:
        """Remove Talkie's own prior injection from captured context."""
        if not self._last_injected:
            return context
        norm_context = context.rstrip()
        norm_last = self._last_injected.rstrip()
        if norm_last and norm_context.endswith(norm_last):
            stripped = norm_context[:-len(norm_last)]
            logger.debug("Stripped %d chars of prior injection, %d remain",
                         len(norm_last), len(stripped))
            self._last_injected = ""
            return stripped
        return context

    def _update_tray_tooltip(self) -> None:
        """Update tray icon tooltip with the active hotkey."""
        if self.tray_icon:
            hotkey = self.config.get("hotkey", "ctrl+win")
            self.tray_icon.title = f"Talkie ({hotkey})"

    def _on_config_saved(self) -> None:
        """Called by settings server when config is saved."""
        self.config = load_config()
        logging.getLogger("talkie").setLevel(self._log_level())
        if self.hotkey_manager:
            self.hotkey_manager.stop()
        self.hotkey_manager = HotkeyManager(
            self.config.get("hotkey", "ctrl+win"), self.on_press, self.on_release
        )
        self.hotkey_manager.start()
        self._update_tray_tooltip()
        set_tone_preset(self.config.get("notification_tone", "pop"))
        logger.info("Config reloaded, hotkey refreshed: %s", self.config.get("hotkey"))

    def create_tray_icon(self) -> None:
        import pystray
        from talkie_modules.icon_generator import get_tray_image
        image = get_tray_image(64)

        hotkey = self.config.get("hotkey", "ctrl+win")
        self.tray_icon = pystray.Icon("Talkie", image, f"Talkie ({hotkey})")
        self._rebuild_tray_menu()

    def _rebuild_tray_menu(self) -> None:
        """Rebuild tray menu with current Recent history items."""
        import pystray
        from talkie_modules.history import get_entries

        entries = get_entries(limit=5)
        if entries:
            recent_items = []
            for entry in entries:
                text_preview = entry["text"][:40] + ("..." if len(entry["text"]) > 40 else "")
                app_label = entry.get("target_app", "")
                label = f"{app_label}: {text_preview}" if app_label else text_preview
                entry_text = entry["text"]
                recent_items.append(
                    pystray.MenuItem(label, lambda _, t=entry_text: self._reinject_from_tray(t))
                )
            recent_submenu = pystray.Menu(*recent_items)
        else:
            recent_submenu = pystray.Menu(
                pystray.MenuItem("No recent dictations", None, enabled=False),
            )

        menu = pystray.Menu(
            pystray.MenuItem("Settings", self.show_settings),
            pystray.MenuItem("Start on Boot", self._toggle_start_on_boot,
                             checked=lambda item: self.config.get("start_on_boot", False),
                             visible=getattr(sys, "frozen", False)),
            pystray.MenuItem("Open Log", self._open_log),
            pystray.MenuItem("Recent", recent_submenu),
            pystray.MenuItem("Quit", self.quit_app),
        )
        if self.tray_icon:
            self.tray_icon.menu = menu

    def _reinject_from_tray(self, text: str) -> None:
        """Re-inject text from a Recent tray menu item into the foreground window."""
        import keyboard as kb
        import pyperclip
        # Brief delay to let the OS restore the previous foreground window after menu dismisses
        time.sleep(0.15)
        pyperclip.copy(text)
        kb.send("ctrl+v")

    def _toggle_start_on_boot(self, icon, item):
        """Toggle autostart from the tray menu."""
        from talkie_modules.autostart import sync_autostart
        new_val = not self.config.get("start_on_boot", False)
        if not sync_autostart(new_val):
            return
        self.config["start_on_boot"] = new_val
        save_config(self.config)
        self._rebuild_tray_menu()

    def _open_log(self, icon: object = None, item: object = None) -> None:
        """Open the log file with the system default handler."""
        try:
            os.startfile(LOG_FILE)
        except Exception as e:
            logger.warning("Could not open log file: %s", e)

    def show_settings(self, icon: object = None, item: object = None) -> None:
        """Open settings in the default browser (Syncthing/qBittorrent pattern)."""
        import webbrowser

        if self._settings_server:
            webbrowser.open(self._settings_server.url)

    def _show_indicator(self, new_state: AppState, success: bool = False) -> None:
        """Thread-safe indicator update — native indicator handles threading internally."""
        if self._indicator:
            self._indicator.on_state_change(new_state, success)

    def on_press(self) -> None:
        if not self.state.transition(AppState.IDLE, AppState.RECORDING):
            logger.debug("Ignoring press — not idle (state=%s)", self.state.state.name)
            return
        logger.info("Holding hotkey...")
        self._show_indicator(AppState.RECORDING)
        self._press_time = time.time()
        self._pending_hwnd, self._pending_process, self._pending_title = get_target_window()
        start_recording()                           # Chime plays immediately

    def on_release(self) -> None:
        if not self.state.transition(AppState.RECORDING, AppState.PROCESSING):
            logger.debug("Ignoring release — not recording (state=%s)", self.state.state.name)
            return

        logger.info("Released hotkey. Processing...")
        self._show_indicator(AppState.PROCESSING)

        target_hwnd = self._pending_hwnd
        press_time = self._press_time
        pending_process = self._pending_process
        pending_title = self._pending_title

        def run_pipeline() -> None:
            # Skip keyboard-based context fallback for terminals — the fallback
            # sends Shift+Home, Ctrl+C, Right which disrupts TUI apps like Claude Code.
            context = get_context(use_fallback=not is_terminal_process(pending_process))
            audio_data = stop_recording()
            clean_context = self._strip_prior_injection(context)
            elapsed = time.time() - press_time
            config = self.config
            profile = resolve_profile(
                config.get("profiles", []), pending_process, pending_title
            )
            if profile:
                logger.info(
                    "Matched profile: %s (for %s)", profile["name"], pending_process
                )
            config = apply_profile(config, profile)
            min_hold = config.get("min_hold_seconds", 1.0)
            silence_threshold = config.get("silence_rms_threshold", 0.005)

            def _discard(reason: str, user_msg: str) -> None:
                logger.info(reason)
                notify_discard(user_msg)
                self._show_indicator(AppState.IDLE, success=False)
                self.state.transition(AppState.PROCESSING, AppState.IDLE)

            if elapsed < min_hold:
                return _discard(
                    f"Recording too short ({elapsed:.1f}s < {min_hold:.1f}s), discarding",
                    "Recording too short",
                )

            if audio_data is None or len(audio_data) == 0:
                return _discard("No audio captured, discarding", "No audio detected")

            rms = compute_rms(audio_data)
            logger.debug("Audio RMS: %.4f (threshold: %.4f)", rms, silence_threshold)
            if rms < silence_threshold:
                return _discard(
                    f"Audio too quiet (RMS={rms:.4f}), discarding",
                    "Audio too quiet",
                )

            play_stop_chime()

            try:
                transcription = transcribe_audio(audio_data, config)
                logger.info("Transcription: %r", transcription[:100])
                if not transcription or transcription.isspace():
                    return _discard("STT returned empty transcription, discarding", "Nothing transcribed")
                logger.info("Context: %r", clean_context[:100] if clean_context else "(empty)")
                processed_text = process_text_llm(
                    transcription, clean_context, config,
                    process_name=pending_process, window_title=pending_title,
                )
                # Prepend a space when the cursor is flush against terminal
                # punctuation. The LLM outputs only the new text (no leading
                # space), so without this "Hello world." + "New sentence." →
                # "Hello world.New sentence." instead of the intended result.
                # If context ends with a space the user already has separation;
                # if it ends with punctuation we add one.
                if (context[-1:] in ".!?"
                        and processed_text
                        and not processed_text[0:1].isspace()):
                    processed_text = " " + processed_text
                inject_text(processed_text, target_hwnd, process_name=pending_process)
                self._last_injected = processed_text
                from talkie_modules.history import add_entry
                add_entry(processed_text, pending_process, pending_title, elapsed)
                self._rebuild_tray_menu()
            except Exception as e:
                is_expected = isinstance(e, TalkieError)
                logger.error(
                    "Pipeline error: %s" if is_expected else "Unexpected pipeline error: %s",
                    e, exc_info=not is_expected,
                )
                notify_error(str(e) if is_expected else f"Unexpected error: {e}")
                self._last_injected = ""
                self._show_indicator(AppState.ERROR)
                self.state.force(AppState.IDLE)
                return

            self._show_indicator(AppState.IDLE, success=True)
            self.state.transition(AppState.PROCESSING, AppState.IDLE)

        threading.Thread(target=run_pipeline, daemon=True).start()

    def quit_app(self, icon: object = None, item: object = None) -> None:
        logger.info("Shutting down Talkie...")
        if self.hotkey_manager:
            self.hotkey_manager.stop()
        if self._indicator:
            self._indicator.destroy()
        if self._settings_server:
            self._settings_server.stop()
        if self.tray_icon:
            self.tray_icon.stop()
        # Schedule fallback exit in case threads don't die cleanly
        threading.Timer(1.0, lambda: os._exit(0)).start()

    def run(self) -> None:
        # 0. Clean up stale update files from a previous update
        from talkie_modules.updater import cleanup_update_files
        cleanup_update_files(BASE_DIR)

        # 0b. Reconcile autostart registry with current exe path
        if self.config.get("start_on_boot"):
            from talkie_modules.autostart import is_autostart_enabled, enable_autostart
            if not is_autostart_enabled():
                enable_autostart()

        # 1. Start hotkey listener
        self.hotkey_manager = HotkeyManager(
            self.config.get("hotkey", "ctrl+win"), self.on_press, self.on_release
        )
        self.hotkey_manager.start()

        # 2. Create and start tray icon in a separate thread
        self.create_tray_icon()
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

        # 3. Start Bottle settings server
        self._settings_server = SettingsServer(
            on_config_saved=self._on_config_saved,
            get_version=lambda: __version__,
            quit_app=self.quit_app,
        )
        self._settings_server.start()

        # 4. Create the native Win32 status indicator
        self._indicator = NativeStatusIndicator()

        # 5. First-run: auto-open Settings in browser if API keys are missing
        missing = get_missing_keys(self.config)
        if missing:
            logger.info("Missing API keys: %s — opening settings", missing)
            threading.Timer(1.0, self.show_settings).start()

        logger.info("Talkie v%s is running.", __version__)

        # 6. Keep main thread alive (everything runs in daemon threads)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.quit_app()


if __name__ == "__main__":
    load_dotenv()

    if not _acquire_single_instance():
        ctypes.windll.user32.MessageBoxW(
            0, "Talkie is already running.", "Talkie", 0x40
        )
        raise SystemExit(1)

    app = TalkieApp()
    app.run()
