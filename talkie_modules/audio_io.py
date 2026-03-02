"""Audio recording and playback for Talkie."""

import os
from typing import Optional

import numpy as np
import numpy.typing as npt
import sounddevice as sd
import soundfile as sf

from talkie_modules.paths import ASSETS_DIR
from talkie_modules.logger import get_logger

logger = get_logger("audio")

START_WAV: str = os.path.join(ASSETS_DIR, "start.wav")
STOP_WAV: str = os.path.join(ASSETS_DIR, "stop.wav")
SAMPLE_RATE: int = 44100
RECORDING_RATE: int = 16000


def _generate_tone(filename: str, freq_start: float, freq_end: float, duration: float = 0.2) -> None:
    """Generate a frequency-sweep tone and save as WAV."""
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
    frequencies = np.linspace(freq_start, freq_end, len(t))
    phase = np.cumsum(frequencies) * 2 * np.pi / SAMPLE_RATE
    audio = np.sin(phase)

    # Envelope to avoid clicks
    attack_samples = int(0.05 * SAMPLE_RATE)
    decay_samples = int(0.05 * SAMPLE_RATE)
    envelope = np.ones_like(audio)
    envelope[:attack_samples] = np.linspace(0, 1, attack_samples)
    envelope[-decay_samples:] = np.linspace(1, 0, decay_samples)
    audio = audio * envelope * 0.5

    os.makedirs(os.path.dirname(filename), exist_ok=True)
    sf.write(filename, audio, SAMPLE_RATE)
    logger.debug("Generated tone: %s", filename)


def ensure_assets() -> None:
    """Generate start/stop chime WAVs if they don't exist."""
    if not os.path.exists(START_WAV):
        _generate_tone(START_WAV, 440, 880)
    if not os.path.exists(STOP_WAV):
        _generate_tone(STOP_WAV, 880, 440)


def play_start_chime() -> None:
    """Play the recording-start chime."""
    data, fs = sf.read(START_WAV)
    sd.play(data, fs)


def play_stop_chime() -> None:
    """Play the recording-stop chime."""
    data, fs = sf.read(STOP_WAV)
    sd.play(data, fs)


# ---------------------------------------------------------------------------
# Module-level recording state (will be replaced by AudioRecorder in Phase 2)
# ---------------------------------------------------------------------------
import threading
import queue

_recording: bool = False
_audio_queue: queue.Queue = queue.Queue()
_recording_thread: Optional[threading.Thread] = None
_recorded_data: list[npt.NDArray] = []


def _record_callback(indata: npt.NDArray, frames: int, time: object, status: sd.CallbackFlags) -> None:
    if status:
        logger.warning("Audio callback status: %s", status)
    if _recording:
        _audio_queue.put(indata.copy())


def start_recording() -> None:
    """Begin capturing audio from the default input device."""
    global _recording, _audio_queue, _recorded_data, _recording_thread
    _recording = True
    _recorded_data = []
    # Drain stale data
    while not _audio_queue.empty():
        _audio_queue.get()

    def record_loop() -> None:
        with sd.InputStream(samplerate=RECORDING_RATE, channels=1, callback=_record_callback):
            while _recording:
                sd.sleep(100)

    _recording_thread = threading.Thread(target=record_loop, daemon=True)
    _recording_thread.start()
    play_start_chime()
    logger.info("Recording started")


def stop_recording() -> Optional[npt.NDArray]:
    """Stop recording and return captured audio as numpy array, or None if empty."""
    global _recording, _recording_thread, _recorded_data
    _recording = False
    play_stop_chime()

    if _recording_thread:
        _recording_thread.join(timeout=5.0)
        if _recording_thread.is_alive():
            logger.warning("Recording thread did not stop within 5s")

    while not _audio_queue.empty():
        _recorded_data.append(_audio_queue.get())

    logger.info("Recording stopped, %d chunks captured", len(_recorded_data))

    if _recorded_data:
        return np.concatenate(_recorded_data, axis=0)
    return np.array([])
