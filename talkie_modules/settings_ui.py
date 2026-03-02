import customtkinter as ctk
import json
from talkie_modules.config_manager import load_config, save_config

class SettingsUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Talkie Settings")
        self.geometry("600x500")
        ctk.set_appearance_mode("dark")
        
        self.config = load_config()
        
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

    def _setup_api_tab(self):
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

    def _setup_hotkey_tab(self):
        tab = self.tabview.tab("Hotkey")
        ctk.CTkLabel(tab, text="Global Hotkey (e.g., alt+space):").pack(pady=10)
        self.hotkey_entry = ctk.CTkEntry(tab, width=200)
        self.hotkey_entry.insert(0, self.config.get("hotkey", "alt+space"))
        self.hotkey_entry.pack(pady=10)

    def _setup_snippets_tab(self):
        tab = self.tabview.tab("Snippets")
        ctk.CTkLabel(tab, text="Snippets (JSON format key:value):").pack(pady=5)
        self.snippets_text = ctk.CTkTextbox(tab, width=400, height=200)
        self.snippets_text.insert("0.0", json.dumps(self.config.get("snippets", {}), indent=4))
        self.snippets_text.pack(pady=5)

    def _setup_vocab_tab(self):
        tab = self.tabview.tab("Vocabulary")
        ctk.CTkLabel(tab, text="Custom Vocabulary (Comma separated):").pack(pady=5)
        self.vocab_text = ctk.CTkTextbox(tab, width=400, height=200)
        self.vocab_text.insert("0.0", ", ".join(self.config.get("custom_vocabulary", [])))
        self.vocab_text.pack(pady=5)

    def save_settings(self):
        self.config["stt_provider"] = self.stt_provider.get()
        self.config["api_provider"] = self.llm_provider.get()
        self.config["openai_key"] = self.openai_key.get()
        self.config["groq_key"] = self.groq_key.get()
        self.config["anthropic_key"] = self.anthropic_key.get()
        self.config["hotkey"] = self.hotkey_entry.get()
        
        try:
            self.config["snippets"] = json.loads(self.snippets_text.get("0.0", "end"))
        except:
            pass
            
        self.config["custom_vocabulary"] = [x.strip() for x in self.vocab_text.get("0.0", "end").split(",") if x.strip()]
        
        save_config(self.config)
        print("Settings saved.")
        self.withdraw() # Hide window, don't destroy it as it's the root now

if __name__ == "__main__":
    app = SettingsUI()
    app.mainloop()
