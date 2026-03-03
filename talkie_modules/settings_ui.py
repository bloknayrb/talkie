"""Settings UI for Talkie using CustomTkinter."""

import json
import threading
from typing import Any, Optional

import customtkinter as ctk

from talkie_modules.config_manager import (
    load_config,
    save_config,
    save_api_key,
    get_api_key,
    validate_api_key_format,
)
from talkie_modules.logger import get_logger

logger = get_logger("settings")


class SettingsUI(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Talkie Settings")
        self.geometry("600x550")
        ctk.set_appearance_mode("dark")

        self.config: dict[str, Any] = load_config()

        self.tabview = ctk.CTkTabview(self, width=580, height=490)
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

        # API key entries — loaded from keyring
        ctk.CTkLabel(tab, text="OpenAI Key:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.openai_key = ctk.CTkEntry(tab, show="*", width=300)
        self.openai_key.insert(0, get_api_key("openai_key"))
        self.openai_key.grid(row=2, column=1, padx=10, pady=5)

        ctk.CTkLabel(tab, text="Groq Key:").grid(row=3, column=0, padx=10, pady=5, sticky="w")
        self.groq_key = ctk.CTkEntry(tab, show="*", width=300)
        self.groq_key.insert(0, get_api_key("groq_key"))
        self.groq_key.grid(row=3, column=1, padx=10, pady=5)

        ctk.CTkLabel(tab, text="Anthropic Key:").grid(row=4, column=0, padx=10, pady=5, sticky="w")
        self.anthropic_key = ctk.CTkEntry(tab, show="*", width=300)
        self.anthropic_key.insert(0, get_api_key("anthropic_key"))
        self.anthropic_key.grid(row=4, column=1, padx=10, pady=5)

        # Test Connection button
        self.test_button = ctk.CTkButton(tab, text="Test Connection", width=140, command=self._test_connection)
        self.test_button.grid(row=5, column=1, padx=10, pady=10, sticky="w")

        self.test_status = ctk.CTkLabel(tab, text="", text_color="gray")
        self.test_status.grid(row=6, column=0, columnspan=2, padx=10, pady=2)

    def _test_connection(self) -> None:
        """Test the currently configured API connection in a background thread."""
        self.test_button.configure(state="disabled", text="Testing...")
        self.test_status.configure(text="", text_color="gray")
        self.update()

        provider = self.llm_provider.get()

        # Map provider to key entry
        key_map = {
            "openai": self.openai_key,
            "groq": self.groq_key,
            "anthropic": self.anthropic_key,
        }
        key_entry = key_map.get(provider)
        if not key_entry:
            self._show_test_result(False, f"Unknown provider: {provider}")
            return

        api_key = key_entry.get()

        # Format validation first
        key_name = f"{provider}_key" if provider != "anthropic" else "anthropic_key"
        if provider == "openai":
            key_name = "openai_key"
        elif provider == "groq":
            key_name = "groq_key"

        format_error = validate_api_key_format(key_name, api_key)
        if format_error:
            self._show_test_result(False, format_error)
            return

        def _run_test() -> None:
            try:
                if provider in ("openai", "groq"):
                    import openai
                    if provider == "openai":
                        client = openai.OpenAI(api_key=api_key, timeout=10)
                    else:
                        client = openai.OpenAI(
                            api_key=api_key,
                            base_url="https://api.groq.com/openai/v1",
                            timeout=10,
                        )
                    # Lightweight test — list models
                    client.models.list()
                    self.after(0, lambda: self._show_test_result(True, f"{provider} connection OK"))
                elif provider == "anthropic":
                    import anthropic
                    client = anthropic.Anthropic(api_key=api_key, timeout=10)
                    # Send a minimal message to verify auth
                    client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=1,
                        messages=[{"role": "user", "content": "hi"}],
                    )
                    self.after(0, lambda: self._show_test_result(True, "Anthropic connection OK"))
            except Exception as e:
                error_msg = str(e)[:80]
                self.after(0, lambda: self._show_test_result(False, error_msg))

        threading.Thread(target=_run_test, daemon=True).start()

    def _show_test_result(self, success: bool, message: str) -> None:
        """Update the test status label on the main thread."""
        color = "green" if success else "red"
        self.test_status.configure(text=message, text_color=color)
        self.test_button.configure(state="normal", text="Test Connection")

    def _setup_hotkey_tab(self) -> None:
        tab = self.tabview.tab("Hotkey")
        ctk.CTkLabel(tab, text="Global Hotkey:").pack(pady=5)

        self.hotkey_frame = ctk.CTkFrame(tab)
        self.hotkey_frame.pack(pady=10)

        self.hotkey_entry = ctk.CTkEntry(self.hotkey_frame, width=200)
        self.hotkey_entry.insert(0, self.config.get("hotkey", "ctrl+win"))
        self.hotkey_entry.pack(side="left", padx=5)

        self.record_button = ctk.CTkButton(
            self.hotkey_frame, text="Record", width=80, command=self._start_hotkey_record
        )
        self.record_button.pack(side="left", padx=5)

        # --- Recording gates ---
        ctk.CTkLabel(tab, text="").pack()  # spacer

        # Min hold duration
        hold_frame = ctk.CTkFrame(tab)
        hold_frame.pack(pady=5, fill="x", padx=20)
        ctk.CTkLabel(hold_frame, text="Min hold (seconds):").pack(side="left", padx=5)
        self.min_hold_var = ctk.DoubleVar(value=self.config.get("min_hold_seconds", 1.0))
        self.min_hold_label = ctk.CTkLabel(hold_frame, text=f"{self.min_hold_var.get():.1f}s", width=40)
        self.min_hold_label.pack(side="right", padx=5)
        self.min_hold_slider = ctk.CTkSlider(
            hold_frame, from_=0.2, to=3.0, number_of_steps=28,
            variable=self.min_hold_var,
            command=lambda v: self.min_hold_label.configure(text=f"{v:.1f}s"),
        )
        self.min_hold_slider.pack(side="right", padx=5, fill="x", expand=True)

        # Silence threshold
        silence_frame = ctk.CTkFrame(tab)
        silence_frame.pack(pady=5, fill="x", padx=20)
        ctk.CTkLabel(silence_frame, text="Silence threshold:").pack(side="left", padx=5)
        self.silence_var = ctk.DoubleVar(value=self.config.get("silence_rms_threshold", 0.01))
        self.silence_label = ctk.CTkLabel(silence_frame, text=f"{self.silence_var.get():.3f}", width=50)
        self.silence_label.pack(side="right", padx=5)
        self.silence_slider = ctk.CTkSlider(
            silence_frame, from_=0.001, to=0.1, number_of_steps=99,
            variable=self.silence_var,
            command=lambda v: self.silence_label.configure(text=f"{v:.3f}"),
        )
        self.silence_slider.pack(side="right", padx=5, fill="x", expand=True)

    def _start_hotkey_record(self) -> None:
        """Record a hotkey in a background thread to avoid freezing the UI."""
        import keyboard

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

    def _finish_hotkey_record(self, new_hotkey: Optional[str]) -> None:
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
        self.config["hotkey"] = self.hotkey_entry.get()
        self.config["min_hold_seconds"] = round(self.min_hold_var.get(), 1)
        self.config["silence_rms_threshold"] = round(self.silence_var.get(), 3)

        # Save API keys to keyring (not config file)
        save_api_key("openai_key", self.openai_key.get())
        save_api_key("groq_key", self.groq_key.get())
        save_api_key("anthropic_key", self.anthropic_key.get())

        # These go in config (keys will be stripped by save_config)
        self.config["openai_key"] = self.openai_key.get()
        self.config["groq_key"] = self.groq_key.get()
        self.config["anthropic_key"] = self.anthropic_key.get()

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
