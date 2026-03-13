"""API client for STT and LLM providers using official SDKs."""

import io
import os
from typing import Any

import numpy as np
import numpy.typing as npt
import soundfile as sf

from talkie_modules.exceptions import TalkieAPIError, TalkieConfigError
from talkie_modules.logger import get_logger
from talkie_modules.providers import PROVIDERS

logger = get_logger("api")

_TIMEOUT = 30  # seconds


def _resolve_key(config: dict[str, Any], config_key: str, env_var: str) -> str:
    """Get API key from config, falling back to env var."""
    key = config.get(config_key, "") or os.environ.get(env_var, "")
    if not key:
        raise TalkieConfigError(f"API key missing: set '{config_key}' in settings or {env_var} env var")
    return key


def _get_openai_client(api_key: str) -> "openai.OpenAI":
    import openai
    return openai.OpenAI(api_key=api_key, timeout=_TIMEOUT)


def _get_groq_client(api_key: str) -> "openai.OpenAI":
    import openai
    return openai.OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
        timeout=_TIMEOUT,
    )


def _get_anthropic_client(api_key: str) -> "anthropic.Anthropic":
    import anthropic
    return anthropic.Anthropic(api_key=api_key, timeout=_TIMEOUT)


def _get_client(provider: str, api_key: str):
    """Get the appropriate SDK client for a provider."""
    if provider == "openai":
        return _get_openai_client(api_key)
    elif provider == "groq":
        return _get_groq_client(api_key)
    elif provider == "anthropic":
        return _get_anthropic_client(api_key)
    raise TalkieConfigError(f"No client factory for provider: {provider}")


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------

def transcribe_audio(audio_data: npt.NDArray, config: dict[str, Any]) -> str:
    """Transcribe audio using the configured STT provider. Returns transcription text."""
    provider: str = config.get("stt_provider", "openai")
    provider_info = PROVIDERS.get(provider)
    if not provider_info:
        raise TalkieConfigError(f"Unknown STT provider: {provider}")
    if provider_info["stt_models"] is None:
        raise TalkieConfigError(f"{provider_info['label']} does not support STT")

    # Resolve key, client, and model from registry
    api_key = _resolve_key(config, provider_info["key_name"], provider_info["key_env"])
    client = _get_client(provider, api_key)
    models = config.get("models", {})
    model = models.get(f"{provider}_stt", provider_info["default_stt"])

    # Convert numpy audio to WAV bytes
    buffer = io.BytesIO()
    sf.write(buffer, audio_data, 16000, format="WAV")
    buffer.seek(0)
    wav_size = buffer.getbuffer().nbytes
    buffer.name = "audio.wav"  # SDK needs a .name attribute

    logger.info("Transcribing with %s (model=%s), WAV buffer: %d bytes", provider, model, wav_size)

    try:
        transcription = client.audio.transcriptions.create(
            model=model,
            file=buffer,
        )
        text = transcription.text
        logger.info("Transcription: %d chars — %r", len(text), text[:100])
        return text
    except Exception as e:
        raise _wrap_api_error(e, provider, "STT") from e


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

def process_text_llm(transcription: str, context: str, config: dict[str, Any]) -> str:
    """Process transcription through an LLM for formatting and context awareness."""
    provider: str = config.get("api_provider", "openai")
    provider_info = PROVIDERS.get(provider)
    if not provider_info:
        raise TalkieConfigError(f"Unknown LLM provider: {provider}")

    # Build system prompt — substitute {vocabulary} and {snippets} placeholders
    vocabulary_list = config.get("custom_vocabulary", [])
    vocabulary_str = ", ".join(vocabulary_list) if vocabulary_list else "(none)"

    snippets_str = ", ".join(
        [f"'{k}' to '{v}'" for k, v in config.get("snippets", {}).items()]
    )
    if not snippets_str:
        snippets_str = "(none)"

    system_prompt = config.get("system_prompt", "")
    system_prompt = system_prompt.replace("{vocabulary}", vocabulary_str)
    system_prompt = system_prompt.replace("{snippets}", snippets_str)
    temperature = config.get("temperature", 0)

    user_prompt = (
        f"<previous_context>{context}</previous_context>\n\n"
        f"<transcription>{transcription}</transcription>"
    )

    # Resolve key, client, and model from registry
    api_key = _resolve_key(config, provider_info["key_name"], provider_info["key_env"])
    client = _get_client(provider, api_key)
    models = config.get("models", {})
    model = models.get(f"{provider}_llm", provider_info["default_llm"])

    logger.info("Processing with %s LLM", provider)

    if provider_info["sdk"] == "openai":
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
            )
            result = response.choices[0].message.content.strip()
            logger.info("LLM response: %d chars", len(result))
            return result
        except Exception as e:
            raise _wrap_api_error(e, provider, "LLM") from e

    elif provider_info["sdk"] == "anthropic":
        try:
            response = client.messages.create(
                model=model,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=1024,
                temperature=temperature,
            )
            result = response.content[0].text.strip()
            logger.info("LLM response: %d chars", len(result))
            return result
        except Exception as e:
            raise _wrap_api_error(e, provider, "LLM") from e

    else:
        raise TalkieConfigError(f"Unsupported SDK type: {provider_info['sdk']}")


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection(provider: str, api_key: str) -> None:
    """Test an API connection. Raises on failure."""
    provider_info = PROVIDERS.get(provider)
    if not provider_info:
        raise TalkieConfigError(f"Unknown provider: {provider}")

    if provider_info["sdk"] == "openai":
        client = _get_client(provider, api_key)
        client.models.list()
    elif provider_info["sdk"] == "anthropic":
        client = _get_client(provider, api_key)
        # Use the last (cheapest) model for the connection test
        test_model = provider_info["llm_models"][-1]
        client.messages.create(
            model=test_model,
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )


# ---------------------------------------------------------------------------
# Error wrapping
# ---------------------------------------------------------------------------

_ERROR_MESSAGES = {
    "AuthenticationError": "Invalid {provider} API key",
    "APITimeoutError": "{provider} {operation} request timed out",
    "APIConnectionError": "Cannot connect to {provider} — check your network",
    "RateLimitError": "{provider} rate limit exceeded — try again shortly",
}


def _wrap_api_error(error: Exception, provider: str, operation: str) -> TalkieAPIError:
    """Convert SDK exceptions into user-friendly TalkieAPIError messages."""
    for mod_name in ("openai", "anthropic"):
        try:
            mod = __import__(mod_name)
            for err_name, msg_template in _ERROR_MESSAGES.items():
                err_class = getattr(mod, err_name, None)
                if err_class and isinstance(error, err_class):
                    return TalkieAPIError(
                        msg_template.format(provider=provider, operation=operation),
                        provider, error,
                    )
        except ImportError:
            continue

    # Fallback
    error_type = type(error).__name__
    msg = str(error)
    logger.error("%s %s error (%s): %s", provider, operation, error_type, msg)
    return TalkieAPIError(f"{provider} {operation} error: {msg}", provider, error)
