# Talkie Roadmap

## Next Up

- **Dictation history** — scrollable log of recent transcriptions with copy/re-inject
- **Per-app profiles** — different LLM prompts or snippet sets depending on the focused app (Slack vs. VS Code vs. email)
- **Streaming transcription** — show partial text as you speak instead of waiting for release
- **Auto-update checker** — notify when a new GitHub release is available
- **Input device selector** — pick which microphone to use from Settings

## Later

- **Local STT option** — whisper.cpp or faster-whisper for fully offline transcription
- **Dictation modes** — toggle between raw transcription (no LLM), cleanup-only, and full context-aware processing
- **Voice commands** — "select all", "new line", "delete that" interpreted as actions rather than text
- **Multi-language support** — language selector for non-English dictation
- **Tray menu quick-toggle** — switch providers/models from the right-click menu without opening Settings
- **macOS / Linux port** — replace Win32-specific code (UI Automation, layered windows, credential manager) with cross-platform alternatives
- **Custom LLM system prompts** — user-editable prompt for how the LLM processes dictation (tone, formatting rules)
- **Plugin system** — hooks for custom post-processing (auto-translate, summarize, format as markdown)
