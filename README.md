<p align="center">
  <img src="assets/banner.png" alt="Talkie — FOSS Voice Typing for Windows PCs" width="600">
</p>

# Talkie

[![AI Slop Inside](https://sladge.net/badge.svg)](https://sladge.net)

Talkie is a local, Windows-based dictation utility designed to be a lightweight clone of "Wispr Flow". It provides a "Hold-to-Talk" experience with context-aware text processing, allowing you to dictate naturally into any application.

## Features

- **Hold-to-Talk Interaction**: Global hotkey (default: `ctrl+win`) allows for instant dictation.
- **Near-Cursor Visual Feedback**: Anti-aliased floating indicator near your cursor shows recording (red with glow), processing (pulsing blue), and success (fading green checkmark) — rendered via Win32 layered window.
- **Context Awareness**: Captures surrounding text and the target application's name and window title, giving the LLM the context it needs for accurate capitalization, spacing, and disambiguation of technical terms.
- **Multi-Provider Support**: Cloud providers (OpenAI, Groq, Anthropic) and local options (whisper.cpp for STT, Ollama for LLM) — mix and match per your needs.
- **Model Selection**: Choose STT and LLM models directly from Settings — no config file editing needed.
- **Per-App Profiles**: Configure different system prompts, snippets, vocabulary, and temperature per application — Talkie automatically applies the matching profile based on the focused window.
- **Built-in Profile Templates**: 6 ready-made templates — each with a tailored system prompt, default snippets, vocabulary, and pre-filled process names. Add from Settings with one click, then customize as needed:
  - **Email** — auto-formats greetings and closings on separate lines
  - **Chat** — preserves informal tone; say "at-mention" or "at sign" before a name to insert `@name`
  - **Code / Terminal** — deterministic output (temperature 0), preserves technical terms verbatim
  - **Documents** — formal prose; say "new paragraph" for explicit paragraph breaks, or "bullet point" / "numbered" / "list item" to start a list
  - **Notes** — spoken markdown commands: "heading", "subheading", "bullet", "checkbox", "numbered" at the start of an utterance insert the corresponding prefix
  - **Browser** — say "hashtag" before a word to insert `#word`; optimized for search and URL fields
- **Custom Snippets**: Define short abbreviations that expand into full text via a structured editor (e.g., `br` -> `Best regards`).
- **Custom Vocabulary**: Ensure specific names, brands, or technical terms are always spelled correctly.
- **Audio Feedback**: Soft pop sounds for recording start/stop — quick 30ms taps instead of harsh beeps.
- **First-Run Onboarding**: Auto-opens Settings with a Quick Start guide and progress badges when API keys are missing.
- **Modern Settings UI**: Dark-themed web interface (Bottle web server + browser) with sidebar navigation — Providers, API Keys, Hotkey, Snippets, Vocabulary, Profiles, and About sections.
- **Secure Key Storage**: API keys stored in Windows Credential Manager, never in config files.
- **Error Notifications**: Windows toast notifications for pipeline errors and discarded recordings.
- **Single Instance**: Only one copy can run at a time — prevents duplicate hotkey hooks.
- **Auto-Updates**: Check for new releases, download, and restart in-place — all from the Settings UI.
- **Dictation History**: Recent transcriptions accessible from the tray icon's "Recent" submenu — copy or re-inject past dictations.
- **Start on Boot**: Optional Windows startup toggle from the tray menu — runs via the user registry, no admin required.
- **Local STT**: Download and run whisper.cpp locally for fully offline speech-to-text — no API key needed.
- **Ollama Integration**: Use locally-hosted LLMs via Ollama for text processing — keeps everything on your machine.
- **Portable Executable**: Run as a single `.exe` with no installation or admin rights required.

## Getting Started

### Download & Run

Download `Talkie.exe` from the latest [Release](https://github.com/bloknayrb/talkie/releases) and run it. A walkie-talkie icon will appear in your system tray.

### Configure API Keys

On first launch, Talkie will automatically open the Settings window showing the Quick Start guide. Enter your API keys and save them — keys are stored securely in Windows Credential Manager.

You can also right-click the tray icon and select **Settings** at any time, or set keys via environment variables (`OPENAI_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`) or a `.env` file.

### Start Dictating

1. Focus on any text field (Notepad, browser, Slack, etc.)
2. Hold your global hotkey (default: `ctrl+win`)
3. Speak clearly
4. Release the hotkey — Talkie processes your audio and injects the text at your cursor

Talkie will notify you when updates are available — install them from the About section in Settings. To launch Talkie automatically when you log in, right-click the tray icon and enable **Start on Boot**.

## Build from Source

### Quick (uv — recommended)

```bash
git clone https://github.com/bloknayrb/talkie.git
cd talkie
uv run --with-requirements requirements.txt python build.py
```

### Alternative (pip + venv)

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
uv run --with-requirements requirements.txt python main.py
```

## Running Tests

```bash
uv run --with-requirements requirements.txt --with pytest python -m pytest tests/ -v
```

## Project Structure

```
main.py                          # App entry point, tray icon, pipeline orchestration
build.py                         # PyInstaller build script
talkie_modules/
    paths.py                     # Single source for all path resolution
    logger.py                    # Structured logging with key-redacting filter
    config_manager.py            # Config loading/saving with keyring integration
    state.py                     # Thread-safe state machine (IDLE/RECORDING/PROCESSING/ERROR)
    exceptions.py                # Custom exception hierarchy
    api_client.py                # STT and LLM API calls with cached SDK clients
    audio_io.py                  # Mic recording, chime caching, and pop/tap generation
    context_capture.py           # Captures surrounding text via UI Automation with clipboard fallback
    profile_matcher.py           # Resolves and applies per-app profiles at dictation time
    profile_templates.py         # Built-in profile templates (Email, Chat, Code, etc.)
    hotkey_manager.py            # Global key hold/release listener
    text_injector.py             # Pastes processed text via clipboard
    history.py                   # Dictation history ring buffer persisted to history.json
    autostart.py                 # Start-on-boot via Windows registry
    updater.py                   # GitHub release checker, downloader, and exe swap
    providers.py                 # Provider/model registry (OpenAI, Groq, Anthropic, Ollama)
    local_whisper.py             # whisper.cpp binary and model management for local STT
    ollama_utils.py              # Ollama reachability check and model listing
    settings_server.py           # Bottle REST API for settings web UI
    status_indicator_native.py   # Win32 native layered window indicator with vectorized rendering
    icon_generator.py            # PIL-generated walkie-talkie icon
    notifications.py             # Windows toast notifications and error chimes
    web_ui/
        settings.html            # Settings SPA (single-page app)
        settings.css             # Dark theme styles
        settings.js              # Client-side logic
assets/
    talkie.ico                   # Multi-resolution app icon (16/32/48/64px)
    start.wav                    # Recording start pop (auto-generated)
    stop.wav                     # Recording stop double-tap (auto-generated)
tests/
    test_state.py                # State machine transitions and thread safety
    test_config_manager.py       # Config merging and API key validation
    test_api_client.py           # Mocked STT/LLM API calls and app context
    test_audio_io.py             # Pop/tap generation and asset versioning
    test_text_injector.py        # Focus restoration and text injection
    test_context_stripping.py    # Prior-injection removal from context
    test_settings_server.py      # Settings API key masking and routes
    test_profile_templates.py    # Template definitions and apply logic
```

## License

This project is licensed under the [MIT License](LICENSE).
