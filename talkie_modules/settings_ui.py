"""Settings UI for Talkie using CustomTkinter."""

import json
from typing import Any

import customtkinter as ctk

from talkie_modules.config_manager import load_config, save_config
from talkie_modules.logger import get_logger

logger = get_logger("settings")


class SettingsUI(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Talkie Settings")
        self.geometry("600x500")
        ctk.set_appearance_mode("dark")

        self.config: dict[str, Any] = load_config()

        self.tabview = ctk.CTkTabview(self, width=580, height=480)
        self.tabview.pack(padx=10, pady=10)

        self.tabview.add("API")
        self.tabview.add("Hotkey")
        self.tabview.add("Snippets")
        self.tabview.add("Vocabulary")

        self._setup_api_tab()
        self._setup_hotkey_tab()
        self._setup_snippets_tab()
        self._setup_vocab_tab()

        self.save_button = ctk.CTkButton(self, text="Save Config", command=self.save_settings)
        self.save_button.pack(pady=10)

    def _setup_api_tab(self) -> None:
        tab = self.tabview.tab("API")

        ctk.CTkLabel(tab, text="STT Provider:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.stt_provider = ctk.CTkComboBox(tab, values=["openai", "groq"], width=200)
        self.stt_provider.set(self.config.get("stt_provider", "openai"))
        self.stt_provider.grid(row=0, column=1, padx=10, pady=5)

        ctk.CTkLabel(tab, text="LLM Provider:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.llm_provider = ctk.CTkComboBox(tab, values=["openai", "groq", "anthropic"], width=200)
        self.llm_provider.set(self.config.get("api_provider", "openai"))
        self.llm_provider.grid(row=1, column=1, padx=10, pady=5)

        ctk.CTkLabel(tab, text="OpenAI Key:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.openai_key = ctk.CTkEntry(tab, show="*", width=300)
        self.openai_key.insert(0, self.config.get("openai_key", ""))
        self.openai_key.grid(row=2, column=1, padx=10, pady=5)

        ctk.CTkLabel(tab, text="Groq Key:").grid(row=3, column=0, padx=10, pady=5, sticky="w")
        self.groq_key = ctk.CTkEntry(tab, show="*", width=300)
        self.groq_key.insert(0, self.config.get("groq_key", ""))
        self.groq_key.grid(row=3, column=1, padx=10, pady=5)

        ctk.CTkLabel(tab, text="Anthropic Key:").grid(row=4, column=0, padx=10, pady=5, sticky="w")
        self.anthropic_key = ctk.CTkEntry(tab, show="*", width=300)
        self.anthropic_key.insert(0, self.config.get("anthropic_key", ""))
        self.anthropic_key.grid(row=4, column=1, padx=10, pady=5)

    def _setup_hotkey_tab(self) -> None:
        tab = self.tabview.tab("Hotkey")
        ctk.CTkLabel(tab, text="Global Hotkey:").pack(pady=5)

        self.hotkey_frame = ctk.CTkFrame(tab)
        self.hotkey_frame.pack(pady=10)

        self.hotkey_entry = ctk.CTkEntry(self.hotkey_frame, width=200)
        self.hotkey_entry.insert(0, self.config.get("hotkey", "alt+space"))
        self.hotkey_entry.pack(side="left", padx=5)

        self.record_button = ctk.CTkButton(
            self.hotkey_frame, text="Record", width=80, command=self._start_hotkey_record
        )
        self.record_button.pack(side="left", padx=5)

    def _start_hotkey_record(self) -> None:
        """Record a hotkey in a background thread to avoid freezing the UI."""
        import keyboard
        import threading

        self.record_button.configure(text="...", state="disabled")
        self.update()

        def _record() -> None:
            try:
                new_hotkey: str = keyboard.read_hotkey(suppress=False)
                self.after(0, lambda: self._finish_hotkey_record(new_hotkey))
            except Exception as e:
                logger.warning("Hotkey recording failed: %s", e)
                self.after(0, lambda: self._finish_hotkey_record(None))

        threading.Thread(target=_record, daemon=True).start()

    def _finish_hotkey_record(self, new_hotkey: str | None) -> None:
        """Callback on main thread after hotkey recording completes."""
        if new_hotkey:
            self.hotkey_entry.delete(0, "end")
            self.hotkey_entry.insert(0, new_hotkey)
        self.record_button.configure(text="Record", state="normal")

    def _setup_snippets_tab(self) -> None:
        tab = self.tabview.tab("Snippets")
        ctk.CTkLabel(tab, text="Snippets (JSON format key:value):").pack(pady=5)
        self.snippets_text = ctk.CTkTextbox(tab, width=400, height=200)
        self.snippets_text.insert("0.0", json.dumps(self.config.get("snippets", {}), indent=4))
        self.snippets_text.pack(pady=5)

    def _setup_vocab_tab(self) -> None:
        tab = self.tabview.tab("Vocabulary")
        ctk.CTkLabel(tab, text="Custom Vocabulary (Comma separated):").pack(pady=5)
        self.vocab_text = ctk.CTkTextbox(tab, width=400, height=200)
        self.vocab_text.insert("0.0", ", ".join(self.config.get("custom_vocabulary", [])))
        self.vocab_text.pack(pady=5)

    def save_settings(self) -> None:
        self.config["stt_provider"] = self.stt_provider.get()
        self.config["api_provider"] = self.llm_provider.get()
        self.config["openai_key"] = self.openai_key.get()
        self.config["groq_key"] = self.groq_key.get()
        self.config["anthropic_key"] = self.anthropic_key.get()
        self.config["hotkey"] = self.hotkey_entry.get()

        try:
            self.config["snippets"] = json.loads(self.snippets_text.get("0.0", "end"))
        except json.JSONDecodeError as e:
            logger.warning("Invalid snippets JSON, keeping previous: %s", e)

        self.config["custom_vocabulary"] = [
            x.strip() for x in self.vocab_text.get("0.0", "end").split(",") if x.strip()
        ]

        save_config(self.config)
        logger.info("Settings saved")
        self.withdraw()


if __name__ == "__main__":
    app = SettingsUI()
    app.mainloop()
