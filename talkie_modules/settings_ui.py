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
from talkie_modules.notifications import show_toast
from talkie_modules.logger import get_logger

logger = get_logger("settings")

# Static model lists per provider (no API fetching needed)
_STT_MODELS: dict[str, list[str]] = {
    "openai": ["whisper-1"],
    "groq": ["whisper-large-v3-turbo", "whisper-large-v3"],
}

_LLM_MODELS: dict[str, list[str]] = {
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
    "anthropic": ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"],
}


class SettingsUI(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Talkie Settings")
        self.geometry("600x620")
        ctk.set_appearance_mode("dark")

        self.config: dict[str, Any] = load_config()

        # First-run banner (hidden by default)
        self._first_run_label = ctk.CTkLabel(
            self, text="", text_color="#facc15", font=("", 13, "bold"),
            wraplength=560,
        )

        self.tabview = ctk.CTkTabview(self, width=580, height=510)
        self.tabview.pack(padx=10, pady=(5, 10))

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

    # ------------------------------------------------------------------
    # First-run guidance
    # ------------------------------------------------------------------

    def show_first_run_message(self, message: str) -> None:
        """Show a guidance banner at the top of the window."""
        self._first_run_label.configure(text=message)
        self._first_run_label.pack(before=self.tabview, padx=10, pady=(10, 0))

    # ------------------------------------------------------------------
    # API tab
    # ------------------------------------------------------------------

    def _setup_api_tab(self) -> None:
        tab = self.tabview.tab("API")
        models = self.config.get("models", {})

        ctk.CTkLabel(tab, text="STT Provider:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.stt_provider = ctk.CTkComboBox(
            tab, values=["openai", "groq"], width=200, command=self._on_stt_provider_change,
        )
        self.stt_provider.set(self.config.get("stt_provider", "openai"))
        self.stt_provider.grid(row=0, column=1, padx=10, pady=5)

        # STT model dropdown
        ctk.CTkLabel(tab, text="STT Model:").grid(row=0, column=2, padx=(20, 5), pady=5, sticky="w")
        stt_prov = self.config.get("stt_provider", "openai")
        stt_model_key = f"{stt_prov}_stt"
        self.stt_model = ctk.CTkComboBox(tab, values=_STT_MODELS.get(stt_prov, [""]), width=200)
        self.stt_model.set(models.get(stt_model_key, _STT_MODELS.get(stt_prov, [""])[0]))
        self.stt_model.grid(row=0, column=3, padx=5, pady=5)

        ctk.CTkLabel(tab, text="LLM Provider:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.llm_provider = ctk.CTkComboBox(
            tab, values=["openai", "groq", "anthropic"], width=200,
            command=self._on_llm_provider_change,
        )
        self.llm_provider.set(self.config.get("api_provider", "openai"))
        self.llm_provider.grid(row=1, column=1, padx=10, pady=5)

        # LLM model dropdown
        ctk.CTkLabel(tab, text="LLM Model:").grid(row=1, column=2, padx=(20, 5), pady=5, sticky="w")
        llm_prov = self.config.get("api_provider", "openai")
        llm_model_key = f"{llm_prov}_llm"
        self.llm_model = ctk.CTkComboBox(tab, values=_LLM_MODELS.get(llm_prov, [""]), width=200)
        self.llm_model.set(models.get(llm_model_key, _LLM_MODELS.get(llm_prov, [""])[0]))
        self.llm_model.grid(row=1, column=3, padx=5, pady=5)

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

        self.test_status = ctk.CTkLabel(tab, text="", text_color="gray", wraplength=500)
        self.test_status.grid(row=6, column=0, columnspan=4, padx=10, pady=2)

    def _on_stt_provider_change(self, provider: str) -> None:
        """Update STT model dropdown when provider changes."""
        models_list = _STT_MODELS.get(provider, [""])
        self.stt_model.configure(values=models_list)
        self.stt_model.set(models_list[0] if models_list else "")

    def _on_llm_provider_change(self, provider: str) -> None:
        """Update LLM model dropdown when provider changes."""
        models_list = _LLM_MODELS.get(provider, [""])
        self.llm_model.configure(values=models_list)
        self.llm_model.set(models_list[0] if models_list else "")

    def _test_connection(self) -> None:
        """Test both STT and LLM connections in a background thread."""
        self.test_button.configure(state="disabled", text="Testing...")
        self.test_status.configure(text="", text_color="gray")
        self.update()

        stt_prov = self.stt_provider.get()
        llm_prov = self.llm_provider.get()

        # Map provider to key entry
        key_map = {
            "openai": self.openai_key,
            "groq": self.groq_key,
            "anthropic": self.anthropic_key,
        }

        def _run_test() -> None:
            from talkie_modules.api_client import test_connection
            results: list[str] = []

            # Test STT provider
            stt_key_entry = key_map.get(stt_prov)
            if stt_key_entry:
                stt_key = stt_key_entry.get()
                stt_key_name = f"{stt_prov}_key"
                fmt_err = validate_api_key_format(stt_key_name, stt_key)
                if fmt_err:
                    results.append(f"STT ({stt_prov}): {fmt_err}")
                else:
                    try:
                        test_connection(stt_prov, stt_key)
                        results.append(f"STT ({stt_prov}): OK")
                    except Exception as e:
                        results.append(f"STT ({stt_prov}): {str(e)[:60]}")

            # Test LLM provider (skip if same provider and already tested OK)
            if llm_prov == stt_prov and results and "OK" in results[-1]:
                results.append(f"LLM ({llm_prov}): OK (same key)")
            else:
                llm_key_entry = key_map.get(llm_prov)
                if llm_key_entry:
                    llm_key = llm_key_entry.get()
                    llm_key_name = f"{llm_prov}_key"
                    fmt_err = validate_api_key_format(llm_key_name, llm_key)
                    if fmt_err:
                        results.append(f"LLM ({llm_prov}): {fmt_err}")
                    else:
                        try:
                            test_connection(llm_prov, llm_key)
                            results.append(f"LLM ({llm_prov}): OK")
                        except Exception as e:
                            results.append(f"LLM ({llm_prov}): {str(e)[:60]}")

            all_ok = all("OK" in r for r in results)
            msg = " | ".join(results)
            self.after(0, lambda: self._show_test_result(all_ok, msg))

        threading.Thread(target=_run_test, daemon=True).start()

    def _show_test_result(self, success: bool, message: str) -> None:
        """Update the test status label on the main thread."""
        color = "green" if success else "red"
        self.test_status.configure(text=message, text_color=color)
        self.test_button.configure(state="normal", text="Test Connection")

    # ------------------------------------------------------------------
    # Hotkey tab
    # ------------------------------------------------------------------

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
        self.silence_var = ctk.DoubleVar(value=self.config.get("silence_rms_threshold", 0.005))
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

    # ------------------------------------------------------------------
    # Snippets tab — structured editor
    # ------------------------------------------------------------------

    def _setup_snippets_tab(self) -> None:
        tab = self.tabview.tab("Snippets")
        ctk.CTkLabel(tab, text="Text Expansion Snippets:").pack(pady=(5, 2))

        # Error/status label for snippet validation
        self._snippets_status = ctk.CTkLabel(tab, text="", text_color="red", wraplength=400)
        self._snippets_status.pack(pady=(0, 2))

        # Scrollable frame for snippet rows
        self._snippets_frame = ctk.CTkScrollableFrame(tab, width=480, height=260)
        self._snippets_frame.pack(pady=5, fill="both", expand=True)

        # Column headers
        header = ctk.CTkFrame(self._snippets_frame)
        header.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(header, text="Trigger", width=120, font=("", 12, "bold")).pack(side="left", padx=5)
        ctk.CTkLabel(header, text="Expansion", font=("", 12, "bold")).pack(side="left", padx=5, fill="x", expand=True)

        self._snippet_rows: list[dict[str, Any]] = []
        snippets = self.config.get("snippets", {})
        for trigger, expansion in snippets.items():
            self._add_snippet_row(trigger, expansion)

        # Add button
        add_btn = ctk.CTkButton(tab, text="+ Add Snippet", width=120, command=lambda: self._add_snippet_row("", ""))
        add_btn.pack(pady=5)

    def _add_snippet_row(self, trigger: str = "", expansion: str = "") -> None:
        """Add a single trigger/expansion row to the snippets editor."""
        row_frame = ctk.CTkFrame(self._snippets_frame)
        row_frame.pack(fill="x", pady=2)

        trigger_entry = ctk.CTkEntry(row_frame, width=120, placeholder_text="trigger")
        trigger_entry.pack(side="left", padx=5)
        if trigger:
            trigger_entry.insert(0, trigger)

        expansion_entry = ctk.CTkEntry(row_frame, placeholder_text="expansion text")
        expansion_entry.pack(side="left", padx=5, fill="x", expand=True)
        if expansion:
            expansion_entry.insert(0, expansion)

        def _remove():
            row_frame.destroy()
            self._snippet_rows[:] = [r for r in self._snippet_rows if r["frame"].winfo_exists()]

        del_btn = ctk.CTkButton(row_frame, text="X", width=30, fg_color="#dc2626", command=_remove)
        del_btn.pack(side="right", padx=5)

        self._snippet_rows.append({
            "frame": row_frame,
            "trigger": trigger_entry,
            "expansion": expansion_entry,
        })

    def _collect_snippets(self) -> Optional[dict[str, str]]:
        """
        Collect snippets from the structured editor.
        Returns dict on success, None on validation failure (sets status label).
        """
        self._snippets_status.configure(text="")
        result: dict[str, str] = {}
        seen_triggers: list[str] = []

        for row in self._snippet_rows:
            if not row["frame"].winfo_exists():
                continue
            trigger = row["trigger"].get().strip()
            expansion = row["expansion"].get().strip()
            if not trigger and not expansion:
                continue  # skip empty rows
            if not trigger:
                self._snippets_status.configure(text="A snippet has an expansion but no trigger.")
                return None
            if trigger in seen_triggers:
                self._snippets_status.configure(text=f"Duplicate trigger: '{trigger}'")
                return None
            seen_triggers.append(trigger)
            result[trigger] = expansion

        return result

    # ------------------------------------------------------------------
    # Vocabulary tab
    # ------------------------------------------------------------------

    def _setup_vocab_tab(self) -> None:
        tab = self.tabview.tab("Vocabulary")
        ctk.CTkLabel(tab, text="Custom Vocabulary (Comma separated):").pack(pady=5)
        self.vocab_text = ctk.CTkTextbox(tab, width=400, height=200)
        self.vocab_text.insert("0.0", ", ".join(self.config.get("custom_vocabulary", [])))
        self.vocab_text.pack(pady=5)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_settings(self) -> bool:
        """
        Save all settings. Returns True on success, False if validation fails.
        On failure the window stays open with an error message.
        """
        # Validate snippets first
        snippets = self._collect_snippets()
        if snippets is None:
            # Switch to Snippets tab to show the error
            self.tabview.set("Snippets")
            return False

        self.config["stt_provider"] = self.stt_provider.get()
        self.config["api_provider"] = self.llm_provider.get()
        self.config["hotkey"] = self.hotkey_entry.get()
        self.config["min_hold_seconds"] = round(self.min_hold_var.get(), 1)
        self.config["silence_rms_threshold"] = round(self.silence_var.get(), 3)

        # Save selected models
        stt_prov = self.stt_provider.get()
        llm_prov = self.llm_provider.get()
        if "models" not in self.config:
            self.config["models"] = {}
        self.config["models"][f"{stt_prov}_stt"] = self.stt_model.get()
        self.config["models"][f"{llm_prov}_llm"] = self.llm_model.get()

        # Save API keys to keyring (not config file)
        save_api_key("openai_key", self.openai_key.get())
        save_api_key("groq_key", self.groq_key.get())
        save_api_key("anthropic_key", self.anthropic_key.get())

        # These go in config (keys will be stripped by save_config)
        self.config["openai_key"] = self.openai_key.get()
        self.config["groq_key"] = self.groq_key.get()
        self.config["anthropic_key"] = self.anthropic_key.get()

        self.config["snippets"] = snippets

        self.config["custom_vocabulary"] = [
            x.strip() for x in self.vocab_text.get("0.0", "end").split(",") if x.strip()
        ]

        save_config(self.config)
        logger.info("Settings saved")
        show_toast("Talkie", "Settings saved")
        self.withdraw()
        return True


if __name__ == "__main__":
    app = SettingsUI()
    app.mainloop()
