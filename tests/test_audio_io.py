"""Tests for audio_io — focused on testable logic (not actual hardware)."""

import os
import tempfile
from unittest.mock import patch

import numpy as np
import pytest

from talkie_modules.audio_io import _generate_tone, ensure_assets, SAMPLE_RATE


class TestGenerateTone:
    def test_creates_file(self, tmp_path) -> None:
        filepath = str(tmp_path / "test_tone.wav")
        _generate_tone(filepath, 440, 880, duration=0.1)
        assert os.path.exists(filepath)
        assert os.path.getsize(filepath) > 0

    def test_correct_duration(self, tmp_path) -> None:
        import soundfile as sf

        filepath = str(tmp_path / "test_tone.wav")
        duration = 0.2
        _generate_tone(filepath, 440, 880, duration=duration)

        data, fs = sf.read(filepath)
        actual_duration = len(data) / fs
        assert abs(actual_duration - duration) < 0.01  # within 10ms


class TestEnsureAssets:
    def test_creates_missing_assets(self, tmp_path) -> None:
        start_wav = str(tmp_path / "assets" / "start.wav")
        stop_wav = str(tmp_path / "assets" / "stop.wav")

        with patch("talkie_modules.audio_io.START_WAV", start_wav), \
             patch("talkie_modules.audio_io.STOP_WAV", stop_wav):
            ensure_assets()
            assert os.path.exists(start_wav)
            assert os.path.exists(stop_wav)

    def test_skips_existing_assets(self, tmp_path) -> None:
        start_wav = str(tmp_path / "assets" / "start.wav")
        stop_wav = str(tmp_path / "assets" / "stop.wav")
        os.makedirs(tmp_path / "assets")

        # Create dummy files
        for path in (start_wav, stop_wav):
            with open(path, "w") as f:
                f.write("existing")

        with patch("talkie_modules.audio_io.START_WAV", start_wav), \
             patch("talkie_modules.audio_io.STOP_WAV", stop_wav):
            ensure_assets()
            # Files should still be the originals (not overwritten)
            with open(start_wav) as f:
                assert f.read() == "existing"
