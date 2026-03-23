"""Audio recording and playback for Talkie."""

import os
import queue
import threading
from typing import Optional

import numpy as np
import numpy.typing as npt
import sounddevice as sd
import soundfile as sf

from talkie_modules.paths import ASSETS_DIR, TONES_DIR
from talkie_modules.logger import get_logger

logger = get_logger("audio")

# Tone WAVs live in TONES_DIR (writable) rather than ASSETS_DIR (_MEIPASS, read-only in prod)
START_WAV: str = os.path.join(TONES_DIR, "start.wav")
STOP_WAV: str = os.path.join(TONES_DIR, "stop.wav")
_PRESET_MARKER: str = os.path.join(TONES_DIR, ".preset")

SAMPLE_RATE: int = 44100
RECORDING_RATE: int = 16000

# Tone preset definitions — each maps to start/stop generation parameters
TONE_PRESETS: dict[str, dict] = {
    "pop": {
        "label": "Pop",
        "description": "Soft pop (default)",
        "start": {"type": "pop", "freq": 800, "duration": 0.03, "volume": 0.25},
        "stop": {"type": "double_tap", "freq": 600, "volume": 0.25},
    },
    "gentle": {
        "label": "Gentle",
        "description": "Softer, lower pitch",
        "start": {"type": "pop", "freq": 440, "duration": 0.05, "volume": 0.20},
        "stop": {"type": "pop", "freq": 520, "duration": 0.05, "volume": 0.20},
    },
    "bright": {
        "label": "Bright",
        "description": "Higher, crisper",
        "start": {"type": "pop", "freq": 1200, "duration": 0.02, "volume": 0.25},
        "stop": {"type": "chord", "freqs": [1000, 1200], "duration": 0.025, "volume": 0.20},
    },
    "minimal": {
        "label": "Minimal",
        "description": "Barely audible ticks",
        "start": {"type": "pop", "freq": 600, "duration": 0.015, "volume": 0.15},
        "stop": {"type": "pop", "freq": 500, "duration": 0.015, "volume": 0.15},
    },
    "silent": {
        "label": "Silent",
        "description": "No sounds",
        "start": None,
        "stop": None,
    },
}


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


def _generate_chord(filename: str, freqs: list[float], duration: float = 0.025,
                    volume: float = 0.20) -> None:
    """Generate a chord: sum of sine waves at given frequencies, exponential decay."""
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
    audio = np.zeros_like(t)
    for freq in freqs:
        audio += np.sin(2 * np.pi * freq * t)
    audio /= len(freqs)  # normalize
    decay_rate = 5.0 / duration
    envelope = np.exp(-decay_rate * t)
    audio = audio * envelope * volume

    os.makedirs(os.path.dirname(filename), exist_ok=True)
    sf.write(filename, audio, SAMPLE_RATE)
    logger.debug("Generated chord sound: %s (%s Hz)", filename, freqs)


def _generate_tone(filename: str, params: dict) -> None:
    """Dispatch to the appropriate generator based on tone type."""
    tone_type = params["type"]
    if tone_type == "pop":
        _generate_pop(filename, freq=params["freq"], duration=params["duration"],
                      volume=params["volume"])
    elif tone_type == "double_tap":
        _generate_double_tap(filename, freq=params["freq"], volume=params["volume"])
    elif tone_type == "chord":
        _generate_chord(filename, freqs=params["freqs"], duration=params["duration"],
                        volume=params["volume"])


_current_preset: str = ""


def _get_current_preset() -> str:
    """Return the current preset name (cached in memory after first read)."""
    global _current_preset
    if _current_preset:
        return _current_preset
    try:
        with open(_PRESET_MARKER, "r") as f:
            _current_preset = f.read().strip()
    except FileNotFoundError:
        pass
    return _current_preset


def _write_preset_marker(name: str) -> None:
    global _current_preset
    os.makedirs(TONES_DIR, exist_ok=True)
    with open(_PRESET_MARKER, "w") as f:
        f.write(name)
    _current_preset = name


def ensure_assets(preset_name: str = "pop") -> None:
    """Generate start/stop chime WAVs for the given preset if needed."""
    if preset_name == "silent":
        return

    preset = TONE_PRESETS.get(preset_name)
    if not preset:
        logger.warning("Unknown tone preset %r, falling back to pop", preset_name)
        preset_name = "pop"
        preset = TONE_PRESETS["pop"]

    # Only regenerate if preset changed or files missing
    current = _get_current_preset()
    start_exists = os.path.isfile(START_WAV)
    stop_exists = os.path.isfile(STOP_WAV)
    if current == preset_name and start_exists and stop_exists:
        return

    logger.info("Generating tone assets for preset: %s", preset_name)
    if preset["start"]:
        _generate_tone(START_WAV, preset["start"])
    if preset["stop"]:
        _generate_tone(STOP_WAV, preset["stop"])
    _write_preset_marker(preset_name)


def set_tone_preset(name: str) -> None:
    """Switch to a new tone preset: regenerate WAVs and clear chime cache."""
    _chime_cache.clear()
    if name == "silent":
        _write_preset_marker(name)
        return
    ensure_assets(name)


_chime_cache: dict[str, tuple[npt.NDArray, int]] = {}


def _play_chime(path: str) -> None:
    """Play a cached chime WAV. Failure is non-fatal."""
    try:
        cached = _chime_cache.get(path)
        if cached is None:
            data, fs = sf.read(path)
            cached = (data, fs)
            _chime_cache[path] = cached
        sd.play(cached[0], cached[1])
    except Exception as e:
        logger.warning("Could not play chime %s: %s", path, e)


def play_start_chime() -> None:
    """Play the recording-start chime. Silent preset skips playback."""
    if _get_current_preset() == "silent":
        return
    _play_chime(START_WAV)


def play_stop_chime() -> None:
    """Play the recording-stop chime. Silent preset skips playback."""
    if _get_current_preset() == "silent":
        return
    _play_chime(STOP_WAV)


def compute_rms(audio: npt.NDArray) -> float:
    """Compute RMS energy of audio data."""
    if len(audio) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio, dtype=np.float32))))


# ---------------------------------------------------------------------------
# AudioRecorder — encapsulates recording state
# ---------------------------------------------------------------------------

class AudioRecorder:
    """Thread-safe audio recorder using sounddevice InputStream."""

    def __init__(self) -> None:
        self._recording: bool = False
        self._audio_queue: queue.Queue = queue.Queue()
        self._recording_thread: Optional[threading.Thread] = None
        self._recorded_data: list[npt.NDArray] = []
        self._recording_error: Optional[str] = None

    def _record_callback(self, indata: npt.NDArray, frames: int, time: object, status: sd.CallbackFlags) -> None:
        if status:
            logger.warning("Audio callback status: %s", status)
        if self._recording:
            self._audio_queue.put(indata.copy())

    def start(self) -> None:
        """Begin capturing audio from the default input device."""
        self._recording = True
        self._recorded_data = []
        self._recording_error = None
        # Drain stale data
        while not self._audio_queue.empty():
            self._audio_queue.get()

        def record_loop() -> None:
            try:
                with sd.InputStream(samplerate=RECORDING_RATE, channels=1, callback=self._record_callback):
                    while self._recording:
                        sd.sleep(100)
            except Exception as e:
                self._recording_error = str(e)
                logger.error("Recording stream failed: %s", e)

        self._recording_thread = threading.Thread(target=record_loop, daemon=True)
        self._recording_thread.start()
        play_start_chime()
        logger.info("Recording started")

    def stop(self) -> Optional[npt.NDArray]:
        """Stop recording and return captured audio as numpy array, or None if empty."""
        self._recording = False

        if self._recording_thread:
            self._recording_thread.join(timeout=5.0)
            if self._recording_thread.is_alive():
                logger.warning("Recording thread did not stop within 5s")

        while not self._audio_queue.empty():
            self._recorded_data.append(self._audio_queue.get())

        if self._recorded_data:
            audio = np.concatenate(self._recorded_data, axis=0)
            duration_s = len(audio) / RECORDING_RATE
            logger.info(
                "Recording stopped: %.1f seconds (%d samples), shape=%s",
                duration_s,
                len(audio),
                audio.shape,
            )
            return audio

        # Distinguish "silence" from "device error"
        if self._recording_error:
            err = self._recording_error
            self._recording_error = None
            logger.error("Recording failed due to device error: %s", err)
            return None

        logger.info("Recording stopped: no audio captured")
        return None


# Backward-compatible module-level aliases (main.py imports these by name)
_default_recorder = AudioRecorder()
start_recording = _default_recorder.start
stop_recording = _default_recorder.stop
