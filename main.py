"""Talkie — hold-to-talk voice dictation app."""

import ctypes
import logging
import os
import threading
import time
from typing import Optional

from dotenv import load_dotenv
from PIL import Image

from talkie_modules.logger import setup_logging, get_logger
from talkie_modules.config_manager import load_config, get_missing_keys
from talkie_modules.audio_io import ensure_assets, start_recording, stop_recording, play_stop_chime, compute_rms
from talkie_modules.hotkey_manager import HotkeyManager
from talkie_modules.context_capture import get_context, get_target_hwnd
from talkie_modules.api_client import transcribe_audio, process_text_llm
from talkie_modules.text_injector import inject_text
from talkie_modules.settings_server import SettingsServer
from talkie_modules.status_indicator_native import NativeStatusIndicator
from talkie_modules.state import StateMachine, AppState
from talkie_modules.notifications import notify_error, notify_discard
from talkie_modules.exceptions import TalkieError
from talkie_modules.paths import LOG_FILE

logger = get_logger("app")

__version__ = "0.6.0"

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
        level = getattr(logging, self.config.get("log_level", "INFO").upper(), logging.INFO)
        setup_logging(level)

        ensure_assets()
        self.hotkey_manager: Optional[HotkeyManager] = None
        self.tray_icon = None
        self.state: StateMachine = StateMachine()
        self._indicator: Optional[NativeStatusIndicator] = None
        self._settings_server: Optional[SettingsServer] = None
        self._pending_context: str = ""
        self._pending_hwnd: int = 0
        self._press_time: float = 0.0
        self._last_injected: str = ""

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
        if self.hotkey_manager:
            self.hotkey_manager.stop()
        self.hotkey_manager = HotkeyManager(
            self.config.get("hotkey", "ctrl+win"), self.on_press, self.on_release
        )
        self.hotkey_manager.start()
        self._update_tray_tooltip()
        logger.info("Config reloaded, hotkey refreshed: %s", self.config.get("hotkey"))

    def create_tray_icon(self) -> None:
        import pystray
        from talkie_modules.icon_generator import get_tray_image
        image = get_tray_image(64)

        hotkey = self.config.get("hotkey", "ctrl+win")
        menu = pystray.Menu(
            pystray.MenuItem("Settings", self.show_settings),
            pystray.MenuItem("Open Log", self._open_log),
            pystray.MenuItem("Quit", self.quit_app),
        )
        self.tray_icon = pystray.Icon("Talkie", image, f"Talkie ({hotkey})", menu)

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
        self._pending_hwnd = get_target_hwnd()
        self._pending_context = get_context()
        start_recording()

    def on_release(self) -> None:
        if not self.state.transition(AppState.RECORDING, AppState.PROCESSING):
            logger.debug("Ignoring release — not recording (state=%s)", self.state.state.name)
            return

        logger.info("Released hotkey. Processing...")
        self._show_indicator(AppState.PROCESSING)

        context = self._pending_context
        target_hwnd = self._pending_hwnd
        press_time = self._press_time

        def run_pipeline() -> None:
            audio_data = stop_recording()
            elapsed = time.time() - press_time
            config = load_config()
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
                logger.info("Transcription: %s", transcription[:100])
                clean_context = self._strip_prior_injection(context)
                processed_text = process_text_llm(transcription, clean_context, config)
                inject_text(processed_text, target_hwnd)
                self._last_injected = processed_text
            except TalkieError as e:
                logger.error("Pipeline error: %s", e)
                notify_error(str(e))
                self._last_injected = ""
                self._show_indicator(AppState.ERROR)
                self.state.force(AppState.IDLE)
                return
            except Exception as e:
                logger.error("Unexpected pipeline error: %s", e, exc_info=True)
                notify_error(f"Unexpected error: {e}")
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
