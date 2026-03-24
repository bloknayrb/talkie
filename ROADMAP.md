# Talkie Roadmap

## Recently Shipped

- **v1.1 — Per-app profiles**: Different system prompts, snippets, vocabulary, and temperature per application, auto-matched by process name or window title.
- **v1.2 — Built-in profile templates**: 6 ready-made templates (Email, Chat, Code/Terminal, Documents, Notes, Browser) with tailored prompts, snippets, and vocabulary. One-click add from Settings, with reset-to-defaults support.
- **v1.3 — Context improvements & performance**: App-context awareness (process name + window title sent to the LLM for disambiguation), improved text context capture with clipboard fallback on key release, SDK client caching, vectorized indicator rendering, and chime audio caching.
- **v1.4.x — Build fixes & auto-updates**: Auto-update checker with in-app download and restart, vcruntime140 bundling for machines without the Visual C++ runtime, terminal TUI safety for context capture, portable single-exe build hardening.
- **v1.5 — Dictation history**: Scrollable log of recent transcriptions in the tray "Recent" submenu with copy and re-inject. Start-on-boot toggle via Windows registry.
- **v1.6.x — Local providers & hardening**: Local STT via whisper.cpp (auto-download of binary and models), Ollama integration for local LLMs, provider/model registry, hotkey suppression fix for Win key leak, MotW stripping for clean update restarts, batch script hardening with logging and rollback checks. v1.6.2 fixes a 404 bug in the Whisper engine download (updated to whisper.cpp v1.8.4 zip format).

## Next Up

- **Streaming transcription** — show partial text as you speak instead of waiting for release
- **Input device selector** — pick which microphone to use from Settings

## Later

- **Start Menu / launcher shortcut** — create a Start Menu entry on first launch so Talkie is findable from Windows search, Flow Launcher, and PowerToys Run without navigating to the exe (#30)
- **Dictation modes** — toggle between raw transcription (no LLM), cleanup-only, and full context-aware processing
- **Voice commands** — "select all", "new line", "delete that" interpreted as actions rather than text
- **Multi-language support** — language selector for non-English dictation
- **Tray menu quick-toggle** — switch providers/models from the right-click menu without opening Settings
- **macOS / Linux port** — replace Win32-specific code (UI Automation, layered windows, credential manager) with cross-platform alternatives
- **Plugin system** — hooks for custom post-processing (auto-translate, summarize, format as markdown)
