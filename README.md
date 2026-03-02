# Talkie

Talkie is a local, Windows-based dictation utility designed to be a lightweight clone of "Wispr Flow". It provides a "Hold-to-Talk" experience with context-aware text processing, allowing you to dictate naturally into any application.

## Features

- **Hold-to-Talk Interaction**: Global hotkey (default: `alt+space`) allows for instant dictation.
- **Context Awareness**: Automatically captures surrounding text to ensure perfect capitalization and spacing.
- **Multi-Provider Support**: Supports OpenAI (Whisper), Groq (Whisper-v3), and Anthropic (Claude) for STT and LLM processing.
- **Custom Snippets**: Define short abbreviations that expand into full text (e.g., `br` -> `Best regards`).
- **Custom Vocabulary**: Ensure specific names, brands, or technical terms are always spelled correctly.
- **Audio Feedback**: Subtle synthetic chimes indicate when recording starts, stops, or fails.
- **Secure Key Storage**: API keys stored in Windows Credential Manager, never in config files.
- **Error Notifications**: Windows toast notifications for pipeline errors instead of silent failures.
- **Portable Executable**: Run as a single `.exe` with no installation or admin rights required.

## Getting Started

### Download & Run

Download `Talkie.exe` from the latest [Release](https://github.com/bloknayrb/talkie/releases) and run it. A blue square icon will appear in your system tray.

### Configure API Keys

Right-click the system tray icon, select **Settings**, enter your API keys, and click **Save Config**. Keys are stored securely in Windows Credential Manager.

You can also set keys via environment variables (`OPENAI_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`) or a `.env` file.

### Start Dictating

1. Focus on any text field (Notepad, browser, Slack, etc.)
2. Hold your global hotkey (default: `alt+space`)
3. Speak clearly
4. Release the hotkey — Talkie processes your audio and injects the text at your cursor

## Build from Source

### Quick (uses your existing Python)

```bash
git clone https://github.com/bloknayrb/talkie.git
cd talkie
pip install -r requirements.txt
python build.py
```

The executable will be in `dist/Talkie.exe`.

### Recommended (clean venv — smallest exe)

Using a virtual environment ensures only Talkie's dependencies are bundled, producing a much smaller executable (~40MB vs 200MB+).

```bash
git clone https://github.com/bloknayrb/talkie.git
cd talkie
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python build.py
```

### Run from source (no build)

```bash
pip install -r requirements.txt
python main.py
```

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

## Project Structure

```
main.py                          # App entry point, tray icon, pipeline orchestration
talkie_modules/
    paths.py                     # Single source for all path resolution
    logger.py                    # Structured logging with key-redacting filter
    config_manager.py            # Config loading/saving with keyring integration
    state.py                     # Thread-safe state machine (IDLE/RECORDING/PROCESSING/ERROR)
    exceptions.py                # Custom exception hierarchy
    api_client.py                # STT and LLM API calls via official SDKs
    audio_io.py                  # Mic recording and chime generation
    context_capture.py           # Captures surrounding text via Windows UI Automation
    hotkey_manager.py            # Global key hold/release listener
    text_injector.py             # Pastes processed text via clipboard
    settings_ui.py               # CustomTkinter settings interface
    notifications.py             # Windows toast notifications and error chimes
tests/
    test_state.py                # State machine transitions and thread safety
    test_config_manager.py       # Config merging and API key validation
    test_api_client.py           # Mocked STT/LLM API calls
    test_audio_io.py             # Tone generation and asset management
```

## License

This project is licensed under the MIT License.
