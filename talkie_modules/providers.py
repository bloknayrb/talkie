"""Single source of truth for provider metadata.

Adding a provider means adding one entry to PROVIDERS — all other modules
derive their constants from this registry.
"""

PROVIDERS = {
    "openai": {
        "label": "OpenAI",
        "key_name": "openai_key",
        "key_env": "OPENAI_API_KEY",
        "key_prefix": "sk-",
        "key_min_length": 20,
        "key_url": "https://platform.openai.com/api-keys",
        "stt_models": ["whisper-1"],
        "llm_models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        "default_stt": "whisper-1",
        "default_llm": "gpt-4o",
        "sdk": "openai",
    },
    "groq": {
        "label": "Groq",
        "key_name": "groq_key",
        "key_env": "GROQ_API_KEY",
        "key_prefix": "gsk_",
        "key_min_length": 20,
        "key_url": "https://console.groq.com/keys",
        "stt_models": ["whisper-large-v3-turbo", "whisper-large-v3"],
        "llm_models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
        "default_stt": "whisper-large-v3-turbo",
        "default_llm": "llama-3.3-70b-versatile",
        "sdk": "openai",
    },
    "anthropic": {
        "label": "Anthropic",
        "key_name": "anthropic_key",
        "key_env": "ANTHROPIC_API_KEY",
        "key_prefix": "sk-ant-",
        "key_min_length": 20,
        "key_url": "https://console.anthropic.com/settings/keys",
        "stt_models": None,
        "llm_models": ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"],
        "default_llm": "claude-sonnet-4-20250514",
        "sdk": "anthropic",
    },
}

# Derived constants — replace all scattered copies
KEY_NAMES = tuple(p["key_name"] for p in PROVIDERS.values())
STT_MODELS = {k: v["stt_models"] for k, v in PROVIDERS.items() if v.get("stt_models")}
LLM_MODELS = {k: v["llm_models"] for k, v in PROVIDERS.items() if v.get("llm_models")}
KEY_PREFIXES = {v["key_name"]: v["key_prefix"] for v in PROVIDERS.values()}
PROVIDER_KEY_MAP = {k: v["key_name"] for k, v in PROVIDERS.items()}
