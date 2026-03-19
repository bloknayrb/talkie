# Talkie Roadmap

## Recently Shipped

- **v1.1 — Per-app profiles**: Different system prompts, snippets, vocabulary, and temperature per application, auto-matched by process name or window title.
- **v1.2 — Built-in profile templates**: 6 ready-made templates (Email, Chat, Code/Terminal, Documents, Notes, Browser) with tailored prompts, snippets, and vocabulary. One-click add from Settings, with reset-to-defaults support.
- **v1.3 — Context improvements & performance**: App-context awareness (process name + window title sent to the LLM for disambiguation), improved text context capture with clipboard fallback on key release, SDK client caching, vectorized indicator rendering, and chime audio caching.

## Next Up

- **Dictation history** — scrollable log of recent transcriptions with copy/re-inject
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
- **Plugin system** — hooks for custom post-processing (auto-translate, summarize, format as markdown)
