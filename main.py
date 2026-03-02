import os
import sys
import threading
import time
from PIL import Image, ImageDraw
import pystray
from talkie_modules.config_manager import load_config
from talkie_modules.audio_io import ensure_assets, start_recording, stop_recording
from talkie_modules.hotkey_manager import HotkeyManager
from talkie_modules.context_capture import get_context
from talkie_modules.api_client import transcribe_audio, process_text_llm
from talkie_modules.text_injector import inject_text
from talkie_modules.settings_ui import SettingsUI

class TalkieApp:
    def __init__(self):
        self.config = load_config()
        ensure_assets()
        self.root = None # This will be our SettingsUI
        self.hotkey_manager = None
        self.tray_icon = None
        self.is_processing = False

    def create_tray_icon(self):
        width = 64
        height = 64
        color1 = "blue"
        color2 = "white"
        image = Image.new('RGB', (width, height), color1)
        dc = ImageDraw.Draw(image)
        dc.rectangle([width // 4, height // 4, width * 3 // 4, height * 3 // 4], fill=color2)
        
        # Use Menu and MenuItem for better tray support
        menu = pystray.Menu(
            pystray.MenuItem('Settings', self.show_settings),
            pystray.MenuItem('Quit', self.quit_app)
        )
        self.tray_icon = pystray.Icon("Talkie", image, "Talkie", menu)

    def show_settings(self):
        # This is called from the tray thread.
        # We must tell the main thread (Tkinter loop) to show the window.
        if self.root:
            self.root.after(0, self._deiconify_root)

    def _deiconify_root(self):
        if self.root:
            self.root.deiconify()
            self.root.focus_force()

    def on_press(self):
        if self.is_processing:
            return
        print("Holding hotkey...")
        self.current_context = get_context()
        start_recording()

    def on_release(self):
        print("Released hotkey. Processing...")
        self.is_processing = True
        audio_data = stop_recording()
        
        def run_pipeline():
            try:
                if audio_data is not None and len(audio_data) > 0:
                    config = load_config()
                    transcription = transcribe_audio(audio_data, config)
                    processed_text = process_text_llm(transcription, self.current_context, config)
                    inject_text(processed_text)
            except Exception as e:
                print(f"Pipeline error: {e}")
            finally:
                self.is_processing = False

        threading.Thread(target=run_pipeline, daemon=True).start()

    def quit_app(self, icon=None, item=None):
        if self.hotkey_manager:
            self.hotkey_manager.stop()
        if self.tray_icon:
            self.tray_icon.stop()
        if self.root:
            self.root.destroy()
        os._exit(0)

    def run(self):
        # 1. Start hotkey listener
        self.hotkey_manager = HotkeyManager(self.config.get("hotkey", "alt+space"), self.on_press, self.on_release)
        self.hotkey_manager.start()
        
        # 2. Create and start tray icon in a separate thread
        self.create_tray_icon()
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
        
        # 3. Initialize the Tkinter app (SettingsUI) on the main thread
        # It starts withdrawn (hidden) by default or we withdraw it immediately.
        self.root = SettingsUI()
        self.root.withdraw() # Start hidden
        
        # 4. Handle window close (X button) - just hide it
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)
        
        print("Talkie is running (Main Thread in Tkinter Loop).")
        self.root.mainloop()

if __name__ == '__main__':
    app = TalkieApp()
    app.run()
