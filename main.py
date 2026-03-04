"""Talkie — hold-to-talk voice dictation app."""

import ctypes
import logging
import os
import threading
import time
from typing import Optional

from dotenv import load_dotenv
from PIL import Image, ImageDraw
import pystray

from talkie_modules.logger import setup_logging, get_logger
from talkie_modules.config_manager import load_config, get_missing_keys
from talkie_modules.audio_io import ensure_assets, start_recording, stop_recording, play_stop_chime, compute_rms
from talkie_modules.hotkey_manager import HotkeyManager
from talkie_modules.context_capture import get_context, get_target_hwnd
from talkie_modules.api_client import transcribe_audio, process_text_llm
from talkie_modules.text_injector import inject_text
from talkie_modules.settings_ui import SettingsUI
from talkie_modules.state import StateMachine, AppState
from talkie_modules.status_indicator import StatusIndicator
from talkie_modules.notifications import notify_error, notify_discard
from talkie_modules.exceptions import TalkieError
from talkie_modules.paths import LOG_FILE

logger = get_logger("app")

# ---------------------------------------------------------------------------
# Single-instance guard (Item 11)
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
        self.root: Optional[SettingsUI] = None
        self.hotkey_manager: Optional[HotkeyManager] = None
        self.tray_icon: Optional[pystray.Icon] = None
        self.state: StateMachine = StateMachine()
        self._indicator: Optional[StatusIndicator] = None
        self._pending_context: str = ""
        self._pending_hwnd: int = 0
        self._press_time: float = 0.0
        self._last_injected: str = ""

    def _strip_prior_injection(self, context: str) -> str:
        """Remove Talkie's own prior injection from captured context."""
        if not self._last_injected:
            return context
        # Normalize trailing whitespace — apps may add spaces/newlines after paste
        norm_context = context.rstrip()
        norm_last = self._last_injected.rstrip()
        if norm_last and norm_context.endswith(norm_last):
            stripped = norm_context[:-len(norm_last)]
            logger.debug("Stripped %d chars of prior injection, %d remain",
                         len(norm_last), len(stripped))
            self._last_injected = ""  # Clear after one use to limit false positives
            return stripped
        return context

    def _update_tray_tooltip(self) -> None:
        """Update tray icon tooltip with the active hotkey."""
        if self.tray_icon:
            hotkey = self.config.get("hotkey", "ctrl+win")
            self.tray_icon.title = f"Talkie ({hotkey})"

    def create_tray_icon(self) -> None:
        width, height = 64, 64
        image = Image.new("RGB", (width, height), "blue")
        dc = ImageDraw.Draw(image)
        dc.rectangle(
            [width // 4, height // 4, width * 3 // 4, height * 3 // 4], fill="white"
        )

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
        if self.root:
            self.root.after(0, self._deiconify_root)

    def _deiconify_root(self, first_run_message: str = "") -> None:
        if self.root:
            self.root.deiconify()
            self.root.focus_force()
            self.root.save_button.configure(command=self._save_settings_and_refresh)
            # Show first-run guidance if applicable
            if first_run_message and hasattr(self.root, "show_first_run_message"):
                self.root.show_first_run_message(first_run_message)

    def _save_settings_and_refresh(self) -> None:
        if self.root:
            saved = self.root.save_settings()
            if saved is False:
                return  # Validation failed, don't refresh
            self.config = load_config()
            if self.hotkey_manager:
                self.hotkey_manager.stop()
            self.hotkey_manager = HotkeyManager(
                self.config.get("hotkey", "ctrl+win"), self.on_press, self.on_release
            )
            self.hotkey_manager.start()
            self._update_tray_tooltip()
            logger.info("Hotkey refreshed: %s", self.config.get("hotkey"))

    def _show_indicator(self, new_state: AppState, success: bool = False) -> None:
        """Thread-safe indicator update via root.after."""
        if self.root and self._indicator:
            self.root.after(0, self._indicator.on_state_change, new_state, success)

    def on_press(self) -> None:
        if not self.state.transition(AppState.IDLE, AppState.RECORDING):
            logger.debug("Ignoring press — not idle (state=%s)", self.state.state.name)
            return
        logger.info("Holding hotkey...")
        self._show_indicator(AppState.RECORDING)
        self._press_time = time.time()
        self._pending_hwnd = get_target_hwnd()  # FIRST — before any I/O
        self._pending_context = get_context()    # May take 150ms+
        start_recording()

    def on_release(self) -> None:
        if not self.state.transition(AppState.RECORDING, AppState.PROCESSING):
            logger.debug("Ignoring release — not recording (state=%s)", self.state.state.name)
            return

        logger.info("Released hotkey. Processing...")
        self._show_indicator(AppState.PROCESSING)

        # Snapshot state to avoid race condition on rapid re-press
        context = self._pending_context
        target_hwnd = self._pending_hwnd
        press_time = self._press_time

        def run_pipeline() -> None:
            # stop_recording() runs here (off the keyboard hook thread) to avoid
            # Windows' LowLevelHooksTimeout killing our key suppression hook.
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

            # Gate 1: minimum hold duration
            if elapsed < min_hold:
                return _discard(
                    f"Recording too short ({elapsed:.1f}s < {min_hold:.1f}s), discarding",
                    "Recording too short",
                )

            # Gate 2: no audio or silence
            if audio_data is None or len(audio_data) == 0:
                return _discard("No audio captured, discarding", "No audio detected")

            rms = compute_rms(audio_data)
            logger.debug("Audio RMS: %.4f (threshold: %.4f)", rms, silence_threshold)
            if rms < silence_threshold:
                return _discard(
                    f"Audio too quiet (RMS={rms:.4f}), discarding",
                    "Audio too quiet",
                )

            play_stop_chime()  # Only when we'll actually process

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

            # Success — show green checkmark
            self._show_indicator(AppState.IDLE, success=True)
            self.state.transition(AppState.PROCESSING, AppState.IDLE)

        threading.Thread(target=run_pipeline, daemon=True).start()

    def quit_app(self, icon: object = None, item: object = None) -> None:
        logger.info("Shutting down Talkie...")
        if self.hotkey_manager:
            self.hotkey_manager.stop()
        if self._indicator:
            self._indicator.destroy()
        if self.tray_icon:
            self.tray_icon.stop()
        if self.root:
            try:
                self.root.quit()
                self.root.destroy()
            except Exception:
                pass
        # Schedule fallback exit in case mainloop doesn't exit cleanly
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

        # 3. Initialize the Tkinter app (SettingsUI) on the main thread
        self.root = SettingsUI()
        self.root.withdraw()

        # 4. Create the near-cursor status indicator
        self._indicator = StatusIndicator(self.root)

        # 5. Handle window close (X button) — just hide it
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)

        # 6. First-run: auto-open Settings if API keys are missing
        missing = get_missing_keys(self.config)
        if missing:
            msg = f"Talkie needs API keys to work.\nMissing: {', '.join(missing)}"
            self.root.after(500, self._deiconify_root, msg)

        logger.info("Talkie is running.")
        self.root.mainloop()


if __name__ == "__main__":
    load_dotenv()

    if not _acquire_single_instance():
        ctypes.windll.user32.MessageBoxW(
            0, "Talkie is already running.", "Talkie", 0x40
        )
        raise SystemExit(1)

    app = TalkieApp()
    app.run()
