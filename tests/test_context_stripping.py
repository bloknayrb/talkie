"""Tests for TalkieApp._strip_prior_injection context stripping."""

import pytest

from main import TalkieApp


@pytest.fixture
def app(monkeypatch):
    """Create a TalkieApp without side effects (config, logging, assets)."""
    monkeypatch.setattr("main.load_config", lambda: {
        "hotkey": "ctrl+win",
        "log_level": "DEBUG",
    })
    monkeypatch.setattr("main.setup_logging", lambda level: None)
    monkeypatch.setattr("main.ensure_assets", lambda: None)
    return TalkieApp()


class TestStripPriorInjection:
    def test_strips_exact_suffix(self, app):
        app._last_injected = "dictated text"
        result = app._strip_prior_injection("Hello dictated text")
        assert result == "Hello "

    def test_no_op_when_no_prior(self, app):
        # _last_injected defaults to ""
        result = app._strip_prior_injection("some context here")
        assert result == "some context here"

    def test_no_op_when_no_match(self, app):
        app._last_injected = "something else"
        result = app._strip_prior_injection("user typed new stuff")
        assert result == "user typed new stuff"

    def test_strips_when_context_equals_last(self, app):
        app._last_injected = "dictated text"
        result = app._strip_prior_injection("dictated text")
        assert result == ""

    def test_empty_context(self, app):
        app._last_injected = "dictated text"
        result = app._strip_prior_injection("")
        assert result == ""

    def test_whitespace_normalization(self, app):
        app._last_injected = "dictated text"
        result = app._strip_prior_injection("Hello dictated text\n")
        assert result == "Hello "

    def test_clears_last_injected_after_strip(self, app):
        """After a successful strip, _last_injected is cleared to limit false positives."""
        app._last_injected = "dictated text"
        app._strip_prior_injection("Hello dictated text")
        assert app._last_injected == ""

    def test_preserves_last_injected_on_no_match(self, app):
        """When no match, _last_injected stays set for the next call."""
        app._last_injected = "dictated text"
        app._strip_prior_injection("user typed new stuff")
        assert app._last_injected == "dictated text"
