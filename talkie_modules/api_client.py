import os
import requests
import io
import soundfile as sf
import numpy as np

def transcribe_audio(audio_data, config):
    """
    Transcribes audio data using the configured STT provider.
    """
    provider = config.get("stt_provider", "openai")
    api_key = ""
    
    if provider == "openai":
        api_key = config.get("openai_key")
        url = "https://api.openai.com/v1/audio/transcriptions"
    elif provider == "groq":
        api_key = config.get("groq_key")
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
    else:
        raise ValueError(f"Unsupported STT provider: {provider}")

    if not api_key:
        raise ValueError(f"API key missing for {provider}")

    # Convert audio to wav format in-memory
    buffer = io.BytesIO()
    sf.write(buffer, audio_data, 16000, format='WAV')
    buffer.seek(0)

    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"file": ("audio.wav", buffer, "audio/wav")}
    data = {"model": "whisper-1"}
    
    # Groq uses different models
    if provider == "groq":
        data["model"] = "whisper-large-v3-turbo"

    response = requests.post(url, headers=headers, files=files, data=data)
    response.raise_for_status()
    return response.json().get("text", "")

def process_text_llm(transcription, context, config):
    """
    Processes the transcription with an LLM for formatting and context awareness.
    """
    provider = config.get("api_provider", "openai")
    api_key = ""
    model = ""
    url = ""
    
    if provider == "openai":
        api_key = config.get("openai_key")
        url = "https://api.openai.com/v1/chat/completions"
        model = "gpt-4o"
    elif provider == "groq":
        api_key = config.get("groq_key")
        url = "https://api.groq.com/openai/v1/chat/completions"
        model = "llama-3.3-70b-versatile"
    elif provider == "anthropic":
        api_key = config.get("anthropic_key")
        url = "https://api.anthropic.com/v1/messages"
        model = "claude-3-5-sonnet-20241022"
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    if not api_key:
        raise ValueError(f"API key missing for {provider}")

    # Prepare snippets and system prompt
    snippets_str = ", ".join([f"'{k}' to '{v}'" for k, v in config.get("snippets", {}).items()])
    system_prompt = config.get("system_prompt", "").format(snippets=snippets_str)
    
    prompt = f"""<previous_context>{context}</previous_context>

<transcription>{transcription}</transcription>"""

    if provider in ["openai", "groq"]:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    
    elif provider == "anthropic":
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 1024,
            "temperature": 0
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()["content"][0]["text"].strip()
