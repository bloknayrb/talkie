"""Local STT via whisper.cpp subprocess.

Downloads whisper-cli.exe and GGML model files on demand, then transcribes
audio by shelling out to the binary. Zero Python ML dependencies.
"""

import io
import os
import subprocess
import tempfile
import threading
import urllib.request
from typing import Callable, Optional

import numpy.typing as npt
import soundfile as sf

from talkie_modules.exceptions import TalkieConfigError, TalkieAPIError
from talkie_modules.logger import get_logger
from talkie_modules.paths import BIN_DIR, MODELS_DIR

logger = get_logger("local_whisper")

_WHISPER_BIN = os.path.join(BIN_DIR, "whisper-cli.exe")

# whisper.cpp release to pull the binary from
_WHISPER_CPP_VERSION = "v1.7.5"
_WHISPER_CPP_BIN_URL = (
    f"https://github.com/ggerganov/whisper.cpp/releases/download/"
    f"{_WHISPER_CPP_VERSION}/whisper-cli-win64.exe"
)

# GGML model URLs from Hugging Face (ggerganov/whisper.cpp)
_MODEL_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
_MODEL_FILES = {
    "tiny": "ggml-tiny.bin",
    "base": "ggml-base.bin",
    "small": "ggml-small.bin",
    "medium": "ggml-medium.bin",
    "large-v3": "ggml-large-v3.bin",
}

# Approximate download sizes in MB for UI display
MODEL_SIZES_MB = {
    "tiny": 75,
    "base": 150,
    "small": 500,
    "medium": 1500,
    "large-v3": 3100,
}

_download_lock = threading.Lock()


def _ensure_dirs() -> None:
    os.makedirs(BIN_DIR, exist_ok=True)
    os.makedirs(MODELS_DIR, exist_ok=True)


def is_binary_available() -> bool:
    """Check if whisper-cli.exe exists."""
    return os.path.isfile(_WHISPER_BIN)


def get_downloaded_models() -> list[str]:
    """Return list of model names that have been downloaded."""
    if not os.path.isdir(MODELS_DIR):
        return []
    downloaded = []
    for name, filename in _MODEL_FILES.items():
        if os.path.isfile(os.path.join(MODELS_DIR, filename)):
            downloaded.append(name)
    return downloaded


def get_model_path(model_name: str) -> str:
    """Return the full path to a model file."""
    filename = _MODEL_FILES.get(model_name)
    if not filename:
        raise TalkieConfigError(f"Unknown whisper model: {model_name}")
    return os.path.join(MODELS_DIR, filename)


def _download_file(
    url: str,
    dest: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> None:
    """Download a file with optional progress callback. Uses temp file + rename for safety."""
    _ensure_dirs()
    dest_dir = os.path.dirname(dest)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=dest_dir, suffix=".tmp")
    os.close(tmp_fd)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Talkie"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)

        os.replace(tmp_path, dest)
    except Exception:
        # Clean up partial download
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def download_binary(
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> None:
    """Download whisper-cli.exe from the whisper.cpp GitHub release."""
    with _download_lock:
        if is_binary_available():
            return
        logger.info("Downloading whisper-cli.exe from %s", _WHISPER_CPP_BIN_URL)
        _download_file(_WHISPER_CPP_BIN_URL, _WHISPER_BIN, progress_cb)
        logger.info("whisper-cli.exe downloaded to %s", _WHISPER_BIN)


def download_model(
    model_name: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> None:
    """Download a GGML model file from Hugging Face."""
    filename = _MODEL_FILES.get(model_name)
    if not filename:
        raise TalkieConfigError(f"Unknown whisper model: {model_name}")

    dest = os.path.join(MODELS_DIR, filename)
    with _download_lock:
        if os.path.isfile(dest):
            return
        url = f"{_MODEL_BASE_URL}/{filename}"
        logger.info("Downloading whisper model %s from %s", model_name, url)
        _download_file(url, dest, progress_cb)
        logger.info("Model %s downloaded to %s", model_name, dest)


def delete_model(model_name: str) -> bool:
    """Delete a downloaded model. Returns True if deleted."""
    path = get_model_path(model_name)
    try:
        os.unlink(path)
        logger.info("Deleted model %s", model_name)
        return True
    except FileNotFoundError:
        return False


def transcribe(audio_data: npt.NDArray, model_name: str) -> str:
    """Transcribe audio using whisper.cpp subprocess.

    Writes audio to a temp WAV file, runs whisper-cli, reads the text output.
    """
    if not is_binary_available():
        raise TalkieConfigError(
            "Local Whisper engine not installed. Download it from Settings → Providers."
        )

    model_path = get_model_path(model_name)
    if not os.path.isfile(model_path):
        raise TalkieConfigError(
            f"Whisper model '{model_name}' not downloaded. Download it from Settings → Providers."
        )

    # Write audio to temp WAV
    tmp_fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(tmp_fd)

    try:
        sf.write(wav_path, audio_data, 16000, format="WAV")

        cmd = [
            _WHISPER_BIN,
            "--model", model_path,
            "--file", wav_path,
            "--output-txt",
            "--no-timestamps",
            "--language", "en",
        ]

        logger.info("Running whisper-cli: model=%s, wav=%d bytes", model_name, os.path.getsize(wav_path))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            logger.error("whisper-cli failed (rc=%d): %s", result.returncode, stderr)
            raise TalkieAPIError(
                f"Local transcription failed: {stderr or 'unknown error'}",
                "local_whisper",
            )

        # whisper-cli --output-txt writes to <input>.txt
        txt_path = wav_path + ".txt"
        try:
            if os.path.isfile(txt_path):
                with open(txt_path, "r", encoding="utf-8") as f:
                    text = f.read().strip()
            else:
                # Fall back to stdout if no txt file produced
                text = result.stdout.strip()
        finally:
            try:
                os.unlink(txt_path)
            except OSError:
                pass

        logger.info("Local transcription: %d chars — %r", len(text), text[:100])
        return text

    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass
