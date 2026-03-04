"""API client for STT and LLM providers using official SDKs."""

import io
import os
from typing import Any

import numpy as np
import numpy.typing as npt
import soundfile as sf

from talkie_modules.exceptions import TalkieAPIError, TalkieConfigError
from talkie_modules.logger import get_logger

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


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------

def transcribe_audio(audio_data: npt.NDArray, config: dict[str, Any]) -> str:
    """Transcribe audio using the configured STT provider. Returns transcription text."""
    provider: str = config.get("stt_provider", "openai")
    models = config.get("models", {})

    if provider == "openai":
        api_key = _resolve_key(config, "openai_key", "OPENAI_API_KEY")
        client = _get_openai_client(api_key)
        model = models.get("openai_stt", "whisper-1")
    elif provider == "groq":
        api_key = _resolve_key(config, "groq_key", "GROQ_API_KEY")
        client = _get_groq_client(api_key)
        model = models.get("groq_stt", "whisper-large-v3-turbo")
    else:
        raise TalkieConfigError(f"Unsupported STT provider: {provider}")

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
    models = config.get("models", {})

    # Build system prompt
    snippets_str = ", ".join(
        [f"'{k}' to '{v}'" for k, v in config.get("snippets", {}).items()]
    )
    system_prompt = config.get("system_prompt", "").format(snippets=snippets_str)

    user_prompt = (
        f"<previous_context>{context}</previous_context>\n\n"
        f"<transcription>{transcription}</transcription>"
    )

    logger.info("Processing with %s LLM", provider)

    if provider in ("openai", "groq"):
        if provider == "openai":
            api_key = _resolve_key(config, "openai_key", "OPENAI_API_KEY")
            client = _get_openai_client(api_key)
            model = models.get("openai_llm", "gpt-4o")
        else:
            api_key = _resolve_key(config, "groq_key", "GROQ_API_KEY")
            client = _get_groq_client(api_key)
            model = models.get("groq_llm", "llama-3.3-70b-versatile")

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
            )
            result = response.choices[0].message.content.strip()
            logger.info("LLM response: %d chars", len(result))
            return result
        except Exception as e:
            raise _wrap_api_error(e, provider, "LLM") from e

    elif provider == "anthropic":
        api_key = _resolve_key(config, "anthropic_key", "ANTHROPIC_API_KEY")
        client = _get_anthropic_client(api_key)
        model = models.get("anthropic_llm", "claude-sonnet-4-20250514")

        try:
            response = client.messages.create(
                model=model,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=1024,
                temperature=0,
            )
            result = response.content[0].text.strip()
            logger.info("LLM response: %d chars", len(result))
            return result
        except Exception as e:
            raise _wrap_api_error(e, provider, "LLM") from e

    else:
        raise TalkieConfigError(f"Unsupported LLM provider: {provider}")


# ---------------------------------------------------------------------------
# Error wrapping
# ---------------------------------------------------------------------------

def test_connection(provider: str, api_key: str) -> None:
    """Test an API connection. Raises on failure."""
    if provider in ("openai", "groq"):
        client = _get_openai_client(api_key) if provider == "openai" else _get_groq_client(api_key)
        client.models.list()
    elif provider == "anthropic":
        client = _get_anthropic_client(api_key)
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )


def _wrap_api_error(error: Exception, provider: str, operation: str) -> TalkieAPIError:
    """Convert SDK exceptions into user-friendly TalkieAPIError messages."""
    error_type = type(error).__name__
    msg = str(error)

    # OpenAI/Groq SDK errors
    try:
        import openai
        if isinstance(error, openai.AuthenticationError):
            return TalkieAPIError(f"Invalid {provider} API key", provider, error)
        if isinstance(error, openai.APITimeoutError):
            return TalkieAPIError(f"{provider} {operation} request timed out", provider, error)
        if isinstance(error, openai.APIConnectionError):
            return TalkieAPIError(f"Cannot connect to {provider} — check your network", provider, error)
        if isinstance(error, openai.RateLimitError):
            return TalkieAPIError(f"{provider} rate limit exceeded — try again shortly", provider, error)
    except ImportError:
        pass

    # Anthropic SDK errors
    try:
        import anthropic
        if isinstance(error, anthropic.AuthenticationError):
            return TalkieAPIError(f"Invalid {provider} API key", provider, error)
        if isinstance(error, anthropic.APITimeoutError):
            return TalkieAPIError(f"{provider} {operation} request timed out", provider, error)
        if isinstance(error, anthropic.APIConnectionError):
            return TalkieAPIError(f"Cannot connect to {provider} — check your network", provider, error)
        if isinstance(error, anthropic.RateLimitError):
            return TalkieAPIError(f"{provider} rate limit exceeded — try again shortly", provider, error)
    except ImportError:
        pass

    # Fallback
    logger.error("%s %s error (%s): %s", provider, operation, error_type, msg)
    return TalkieAPIError(f"{provider} {operation} error: {msg}", provider, error)
