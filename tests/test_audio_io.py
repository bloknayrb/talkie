"""Tests for audio_io — focused on testable logic (not actual hardware)."""

import os
import tempfile
from unittest.mock import patch

import numpy as np
import pytest

from talkie_modules.audio_io import (
    _generate_pop,
    _generate_double_tap,
    _needs_regeneration,
    ensure_assets,
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


class TestNeedsRegeneration:
    def test_missing_file(self, tmp_path) -> None:
        assert _needs_regeneration(str(tmp_path / "nonexistent.wav")) is True

    def test_small_file_ok(self, tmp_path) -> None:
        filepath = str(tmp_path / "small.wav")
        _generate_pop(filepath, freq=800, duration=0.03, volume=0.25)
        assert _needs_regeneration(filepath) is False

    def test_large_file_regenerated(self, tmp_path) -> None:
        filepath = str(tmp_path / "large.wav")
        # Create a file larger than threshold (old-style 200ms sweep)
        with open(filepath, "wb") as f:
            f.write(b"\x00" * 15000)
        assert _needs_regeneration(filepath) is True


class TestEnsureAssets:
    def test_creates_missing_assets(self, tmp_path) -> None:
        start_wav = str(tmp_path / "assets" / "start.wav")
        stop_wav = str(tmp_path / "assets" / "stop.wav")

        with patch("talkie_modules.audio_io.START_WAV", start_wav), \
             patch("talkie_modules.audio_io.STOP_WAV", stop_wav):
            ensure_assets()
            assert os.path.exists(start_wav)
            assert os.path.exists(stop_wav)

    def test_skips_small_existing_assets(self, tmp_path) -> None:
        """Small WAVs (new-style pops) should not be regenerated."""
        start_wav = str(tmp_path / "assets" / "start.wav")
        stop_wav = str(tmp_path / "assets" / "stop.wav")
        os.makedirs(tmp_path / "assets")

        # Create small files that look like valid new-style pops
        _generate_pop(start_wav, freq=800, duration=0.03, volume=0.25)
        _generate_double_tap(stop_wav, freq=600, volume=0.25)

        start_mtime = os.path.getmtime(start_wav)
        stop_mtime = os.path.getmtime(stop_wav)

        with patch("talkie_modules.audio_io.START_WAV", start_wav), \
             patch("talkie_modules.audio_io.STOP_WAV", stop_wav):
            ensure_assets()
            # Files should not have been regenerated
            assert os.path.getmtime(start_wav) == start_mtime
            assert os.path.getmtime(stop_wav) == stop_mtime

    def test_regenerates_large_assets(self, tmp_path) -> None:
        """Large WAVs (old-style 200ms sweeps) should be regenerated."""
        start_wav = str(tmp_path / "assets" / "start.wav")
        stop_wav = str(tmp_path / "assets" / "stop.wav")
        os.makedirs(tmp_path / "assets")

        # Create large dummy files simulating old-style WAVs
        for path in (start_wav, stop_wav):
            with open(path, "wb") as f:
                f.write(b"\x00" * 15000)

        with patch("talkie_modules.audio_io.START_WAV", start_wav), \
             patch("talkie_modules.audio_io.STOP_WAV", stop_wav):
            ensure_assets()
            # Files should have been regenerated (new-style, smaller)
            assert os.path.getsize(start_wav) < 12000
            assert os.path.getsize(stop_wav) < 12000
