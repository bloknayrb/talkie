import json
import os
import sys

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_FILE = os.path.join(get_base_dir(), 'config.json')

DEFAULT_CONFIG = {
    "api_provider": "openai",
    "stt_provider": "openai",
    "openai_key": "",
    "groq_key": "",
    "anthropic_key": "",
    "hotkey": "alt+space",
    "snippets": {
        "gm": "Good morning",
        "br": "Best regards"
    },
    "custom_vocabulary": ["Talkie", "Wispr Flow"],
    "system_prompt": "You are an expert transcriber. Transcribe the following audio based on the provided <previous_context>. " 
                     "If the context ends mid-sentence, continue it logically with appropriate capitalization and spacing. " 
                     "If context ends with a period, start the next sentence with an uppercase letter. " 
                     "Remove filler words, self-corrections, and apply custom vocabulary spellings. " 
                     "Expand the following snippets: {snippets}. " 
                     "Output ONLY the final processed text."
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    
    with open(CONFIG_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return DEFAULT_CONFIG

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
