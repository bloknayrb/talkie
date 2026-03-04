"""Audio recording and playback for Talkie."""

import os
import queue
import threading
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

# Old-style WAVs (200ms sweeps) are ~17KB; new pops/taps are <10KB
_OLD_WAV_SIZE_THRESHOLD = 12000


def _generate_pop(filename: str, freq: float = 800, duration: float = 0.03,
                  volume: float = 0.25) -> None:
    """
    Generate a soft pop sound: single-cycle sine with fast exponential decay.

    Args:
        filename: Output WAV path
        freq: Base frequency in Hz
        duration: Total duration in seconds
        volume: Peak amplitude (0.0-1.0)
    """
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
    # Single-cycle sine
    audio = np.sin(2 * np.pi * freq * t)
    # Fast exponential decay envelope
    decay_rate = 5.0 / duration  # Decays to ~0.7% by end
    envelope = np.exp(-decay_rate * t)
    audio = audio * envelope * volume

    os.makedirs(os.path.dirname(filename), exist_ok=True)
    sf.write(filename, audio, SAMPLE_RATE)
    logger.debug("Generated pop sound: %s (%.0fHz, %.0fms)", filename, freq, duration * 1000)


def _generate_double_tap(filename: str, freq: float = 600, volume: float = 0.25) -> None:
    """
    Generate a double-tap sound: two soft pops 40ms apart (~100ms total).

    Slightly lower pitch than the start pop to distinguish audibly.
    """
    pop_duration = 0.03  # 30ms per pop
    gap_duration = 0.04  # 40ms gap
    total_duration = pop_duration + gap_duration + pop_duration

    t = np.linspace(0, total_duration, int(SAMPLE_RATE * total_duration), False)
    audio = np.zeros_like(t)

    # First pop
    pop1_end = int(SAMPLE_RATE * pop_duration)
    t1 = t[:pop1_end]
    decay1 = np.exp(-5.0 / pop_duration * t1)
    audio[:pop1_end] = np.sin(2 * np.pi * freq * t1) * decay1

    # Second pop (after gap)
    pop2_start = int(SAMPLE_RATE * (pop_duration + gap_duration))
    pop2_samples = len(t) - pop2_start
    t2 = np.linspace(0, pop2_samples / SAMPLE_RATE, pop2_samples, False)
    decay2 = np.exp(-5.0 / pop_duration * t2)
    audio[pop2_start:] = np.sin(2 * np.pi * freq * t2) * decay2

    audio = audio * volume

    os.makedirs(os.path.dirname(filename), exist_ok=True)
    sf.write(filename, audio, SAMPLE_RATE)
    logger.debug("Generated double-tap sound: %s (%.0fHz)", filename, freq)


def _needs_regeneration(filepath: str) -> bool:
    """Check if a WAV file needs regeneration (missing or old-style large file)."""
    if not os.path.exists(filepath):
        return True
    try:
        size = os.path.getsize(filepath)
        if size > _OLD_WAV_SIZE_THRESHOLD:
            logger.info("Regenerating %s (old-style WAV, %d bytes)", filepath, size)
            return True
    except OSError:
        return True
    return False


def ensure_assets() -> None:
    """Generate start/stop chime WAVs if they don't exist or are old-style."""
    if _needs_regeneration(START_WAV):
        _generate_pop(START_WAV, freq=800, duration=0.03, volume=0.25)
    if _needs_regeneration(STOP_WAV):
        _generate_double_tap(STOP_WAV, freq=600, volume=0.25)


def play_start_chime() -> None:
    """Play the recording-start chime. Failure is non-fatal."""
    try:
        data, fs = sf.read(START_WAV)
        sd.play(data, fs)
    except Exception as e:
        logger.warning("Could not play start chime: %s", e)


def play_stop_chime() -> None:
    """Play the recording-stop chime. Failure is non-fatal."""
    try:
        data, fs = sf.read(STOP_WAV)
        sd.play(data, fs)
    except Exception as e:
        logger.warning("Could not play stop chime: %s", e)


def compute_rms(audio: npt.NDArray) -> float:
    """Compute RMS energy of audio data."""
    if len(audio) == 0:
        return 0.0
    return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))


# ---------------------------------------------------------------------------
# Module-level recording state
# ---------------------------------------------------------------------------

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

    if _recording_thread:
        _recording_thread.join(timeout=5.0)
        if _recording_thread.is_alive():
            logger.warning("Recording thread did not stop within 5s")

    while not _audio_queue.empty():
        _recorded_data.append(_audio_queue.get())

    if _recorded_data:
        audio = np.concatenate(_recorded_data, axis=0)
        duration_s = len(audio) / RECORDING_RATE
        logger.info(
            "Recording stopped: %.1f seconds (%d samples), shape=%s",
            duration_s,
            len(audio),
            audio.shape,
        )
        return audio

    logger.info("Recording stopped: no audio captured")
    return None
