# Talkie 🎙️

Talkie is a local, Windows-based dictation utility designed to be a lightweight clone of "Wispr Flow". It provides a "Hold-to-Talk" experience with context-aware text processing, allowing you to dictate naturally into any application.

## ✨ Features

- **Hold-to-Talk Interaction**: Global hotkey (default: `alt+space`) allows for instant dictation.
- **Context Awareness**: Automatically captures surrounding text to ensure perfect capitalization and spacing.
- **Multi-Provider Support**: Supports OpenAI (Whisper), Groq (Whisper-v3), and Anthropic (Claude) for STT and LLM processing.
- **Custom Snippets**: Define short abbreviations that expand into full text (e.g., `br` -> `Best regards`).
- **Custom Vocabulary**: Ensure specific names, brands, or technical terms are always spelled correctly.
- **Audio Feedback**: Subtle synthetic chimes indicate when recording starts, stops, or fails.
- **Portable Executable**: Run as a single `.exe` with no installation or admin rights required.

## 🚀 Getting Started

### 1. Download & Run
- Download `Talkie.exe` from the latest [Release](https://github.com/bloknayrb/talkie/releases).
- Launch the application. You will see a blue square icon in your system tray.

### 2. Configure API Keys
- Right-click the system tray icon and select **Settings**.
- Enter your API keys for OpenAI, Groq, or Anthropic.
- Click **Save Config**.

### 3. Start Dictating
- Focus on any text field (Notepad, Browser, Slack, etc.).
- Hold your global hotkey (default: `alt+space`).
- Speak clearly.
- Release the hotkey. Talkie will process your audio and inject the text at your cursor.

## 🛠️ Build from Source

If you want to build the executable yourself:

1. **Clone the repository:**
   ```bash
   git clone https://github.com/bloknayrb/talkie.git
   cd talkie
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the build script:**
   ```bash
   python build.py
   ```
   The standalone executable will be generated in the `dist/` folder.

## 📂 Project Structure

- `main.py`: The central orchestrator and system tray manager.
- `talkie_modules/`:
  - `api_client.py`: Handles STT and LLM API requests.
  - `audio_io.py`: Manages mic recording and chime generation.
  - `config_manager.py`: Loads and saves `config.json`.
  - `context_capture.py`: Grabs surrounding text using Windows UI Automation.
  - `hotkey_manager.py`: Listens for global key hold/release events.
  - `settings_ui.py`: The CustomTkinter settings interface.
  - `text_injector.py`: Safely pastes text via clipboard.

## 📝 License

This project is licensed under the MIT License.
