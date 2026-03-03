"""Talkie — hold-to-talk voice dictation app."""

import logging
import os
import sys
import threading
import time
from typing import Optional

from dotenv import load_dotenv
from PIL import Image, ImageDraw
import pystray

from talkie_modules.logger import setup_logging, get_logger
from talkie_modules.config_manager import load_config
from talkie_modules.audio_io import ensure_assets, start_recording, stop_recording, play_stop_chime, compute_rms
from talkie_modules.hotkey_manager import HotkeyManager
from talkie_modules.context_capture import get_context
from talkie_modules.api_client import transcribe_audio, process_text_llm
from talkie_modules.text_injector import inject_text
from talkie_modules.settings_ui import SettingsUI
from talkie_modules.state import StateMachine, AppState
from talkie_modules.notifications import notify_error
from talkie_modules.exceptions import TalkieError

logger = get_logger("app")

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
        self._pending_context: str = ""
        self._press_time: float = 0.0

    def create_tray_icon(self) -> None:
        width, height = 64, 64
        image = Image.new("RGB", (width, height), "blue")
        dc = ImageDraw.Draw(image)
        dc.rectangle(
            [width // 4, height // 4, width * 3 // 4, height * 3 // 4], fill="white"
        )

        menu = pystray.Menu(
            pystray.MenuItem("Settings", self.show_settings),
            pystray.MenuItem("Quit", self.quit_app),
        )
        self.tray_icon = pystray.Icon("Talkie", image, "Talkie", menu)

    def show_settings(self) -> None:
        if self.root:
            self.root.after(0, self._deiconify_root)

    def _deiconify_root(self) -> None:
        if self.root:
            self.root.deiconify()
            self.root.focus_force()
            self.root.save_button.configure(command=self._save_settings_and_refresh)

    def _save_settings_and_refresh(self) -> None:
        if self.root:
            self.root.save_settings()
            self.config = load_config()
            if self.hotkey_manager:
                self.hotkey_manager.stop()
            self.hotkey_manager = HotkeyManager(
                self.config.get("hotkey", "ctrl+win"), self.on_press, self.on_release
            )
            self.hotkey_manager.start()
            logger.info("Hotkey refreshed: %s", self.config.get("hotkey"))

    def on_press(self) -> None:
        if not self.state.transition(AppState.IDLE, AppState.RECORDING):
            logger.debug("Ignoring press — not idle (state=%s)", self.state.state.name)
            return
        logger.info("Holding hotkey...")
        self._press_time = time.time()
        self._pending_context = get_context()
        start_recording()

    def on_release(self) -> None:
        if not self.state.transition(AppState.RECORDING, AppState.PROCESSING):
            logger.debug("Ignoring release — not recording (state=%s)", self.state.state.name)
            return

        logger.info("Released hotkey. Processing...")

        # Snapshot context and press time to avoid race condition on rapid re-press
        context = self._pending_context
        press_time = self._press_time

        def run_pipeline() -> None:
            # stop_recording() runs here (off the keyboard hook thread) to avoid
            # Windows' LowLevelHooksTimeout killing our key suppression hook.
            audio_data = stop_recording()
            elapsed = time.time() - press_time
            config = load_config()
            min_hold = config.get("min_hold_seconds", 1.0)
            silence_threshold = config.get("silence_rms_threshold", 0.01)

            # Gate 1: minimum hold duration
            if elapsed < min_hold:
                logger.info("Recording too short (%.1fs < %.1fs), discarding", elapsed, min_hold)
                self.state.transition(AppState.PROCESSING, AppState.IDLE)
                return

            # Gate 2: silence detection
            if audio_data is not None and len(audio_data) > 0:
                rms = compute_rms(audio_data)
                logger.debug("Audio RMS: %.4f (threshold: %.4f)", rms, silence_threshold)
                if rms < silence_threshold:
                    logger.info("Audio too quiet (RMS=%.4f), discarding", rms)
                    self.state.transition(AppState.PROCESSING, AppState.IDLE)
                    return
            else:
                logger.info("No audio captured, discarding")
                self.state.transition(AppState.PROCESSING, AppState.IDLE)
                return

            play_stop_chime()  # Only when we'll actually process

            try:
                transcription = transcribe_audio(audio_data, config)
                logger.info("Transcription: %s", transcription[:100])
                processed_text = process_text_llm(transcription, context, config)
                inject_text(processed_text)
            except TalkieError as e:
                logger.error("Pipeline error: %s", e)
                notify_error(str(e))
                self.state.force(AppState.IDLE)
                return
            except Exception as e:
                logger.error("Unexpected pipeline error: %s", e, exc_info=True)
                notify_error(f"Unexpected error: {e}")
                self.state.force(AppState.IDLE)
                return
            self.state.transition(AppState.PROCESSING, AppState.IDLE)

        threading.Thread(target=run_pipeline, daemon=True).start()

    def quit_app(self, icon: object = None, item: object = None) -> None:
        logger.info("Shutting down Talkie...")
        if self.hotkey_manager:
            self.hotkey_manager.stop()
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

        # 4. Handle window close (X button) — just hide it
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)

        logger.info("Talkie is running.")
        self.root.mainloop()


if __name__ == "__main__":
    load_dotenv()
    app = TalkieApp()
    app.run()
