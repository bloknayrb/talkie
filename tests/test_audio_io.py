"""Tests for audio_io — focused on testable logic (not actual hardware)."""

import os
from unittest.mock import patch

import numpy as np
import pytest

from talkie_modules.audio_io import (
    _generate_pop,
    _generate_double_tap,
    _generate_chord,
    ensure_assets,
    set_tone_preset,
    TONE_PRESETS,
    SAMPLE_RATE,
)


class TestGeneratePop:
    def test_creates_file(self, tmp_path) -> None:
        filepath = str(tmp_path / "test_pop.wav")
        _generate_pop(filepath, freq=800, duration=0.03, volume=0.25)
        assert os.path.exists(filepath)
        assert os.path.getsize(filepath) > 0

    def test_short_duration(self, tmp_path) -> None:
        import soundfile as sf

        filepath = str(tmp_path / "test_pop.wav")
        _generate_pop(filepath, freq=800, duration=0.03, volume=0.25)
        data, fs = sf.read(filepath)
        actual_duration = len(data) / fs
        assert actual_duration < 0.05  # Should be ~30ms


class TestGenerateDoubleTap:
    def test_creates_file(self, tmp_path) -> None:
        filepath = str(tmp_path / "test_double.wav")
        _generate_double_tap(filepath, freq=600, volume=0.25)
        assert os.path.exists(filepath)
        assert os.path.getsize(filepath) > 0

    def test_longer_than_single_pop(self, tmp_path) -> None:
        import soundfile as sf

        pop_path = str(tmp_path / "pop.wav")
        double_path = str(tmp_path / "double.wav")
        _generate_pop(pop_path, freq=800, duration=0.03, volume=0.25)
        _generate_double_tap(double_path, freq=600, volume=0.25)

        pop_data, _ = sf.read(pop_path)
        double_data, _ = sf.read(double_path)
        assert len(double_data) > len(pop_data)


class TestGenerateChord:
    def test_creates_file(self, tmp_path) -> None:
        filepath = str(tmp_path / "chord.wav")
        _generate_chord(filepath, freqs=[1000, 1200], duration=0.025, volume=0.20)
        assert os.path.exists(filepath)
        assert os.path.getsize(filepath) > 0


class TestTonePresets:
    def test_all_presets_have_required_keys(self) -> None:
        for name, preset in TONE_PRESETS.items():
            assert "label" in preset, f"{name} missing label"
            assert "description" in preset, f"{name} missing description"
            assert "start" in preset, f"{name} missing start"
            assert "stop" in preset, f"{name} missing stop"

    def test_silent_preset_has_none_tones(self) -> None:
        assert TONE_PRESETS["silent"]["start"] is None
        assert TONE_PRESETS["silent"]["stop"] is None


class TestEnsureAssets:
    def test_creates_missing_assets(self, tmp_path) -> None:
        start_wav = str(tmp_path / "start.wav")
        stop_wav = str(tmp_path / "stop.wav")
        marker = str(tmp_path / ".preset")

        with patch("talkie_modules.audio_io.START_WAV", start_wav), \
             patch("talkie_modules.audio_io.STOP_WAV", stop_wav), \
             patch("talkie_modules.audio_io._PRESET_MARKER", marker):
            ensure_assets("pop")
            assert os.path.exists(start_wav)
            assert os.path.exists(stop_wav)

    def test_skips_if_preset_matches(self, tmp_path) -> None:
        start_wav = str(tmp_path / "start.wav")
        stop_wav = str(tmp_path / "stop.wav")
        marker = str(tmp_path / ".preset")

        with patch("talkie_modules.audio_io.START_WAV", start_wav), \
             patch("talkie_modules.audio_io.STOP_WAV", stop_wav), \
             patch("talkie_modules.audio_io._PRESET_MARKER", marker):
            ensure_assets("pop")
            start_mtime = os.path.getmtime(start_wav)
            ensure_assets("pop")
            assert os.path.getmtime(start_wav) == start_mtime

    def test_regenerates_on_preset_change(self, tmp_path) -> None:
        start_wav = str(tmp_path / "start.wav")
        stop_wav = str(tmp_path / "stop.wav")
        marker = str(tmp_path / ".preset")

        with patch("talkie_modules.audio_io.START_WAV", start_wav), \
             patch("talkie_modules.audio_io.STOP_WAV", stop_wav), \
             patch("talkie_modules.audio_io._PRESET_MARKER", marker):
            ensure_assets("pop")
            pop_size = os.path.getsize(start_wav)
            ensure_assets("gentle")
            gentle_size = os.path.getsize(start_wav)
            # Different preset should produce different file
            assert pop_size != gentle_size

    def test_silent_skips_generation(self, tmp_path) -> None:
        start_wav = str(tmp_path / "start.wav")
        with patch("talkie_modules.audio_io.START_WAV", start_wav):
            ensure_assets("silent")
            assert not os.path.exists(start_wav)


class TestSetTonePreset:
    def test_clears_cache(self, tmp_path) -> None:
        start_wav = str(tmp_path / "start.wav")
        stop_wav = str(tmp_path / "stop.wav")
        marker = str(tmp_path / ".preset")

        with patch("talkie_modules.audio_io.START_WAV", start_wav), \
             patch("talkie_modules.audio_io.STOP_WAV", stop_wav), \
             patch("talkie_modules.audio_io._PRESET_MARKER", marker), \
             patch("talkie_modules.audio_io._chime_cache", {"old": "data"}) as cache:
            set_tone_preset("gentle")
            assert len(cache) == 0
