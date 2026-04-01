"""Tests for text_injector — focus restore and text injection."""

from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# _restore_focus tests
# ---------------------------------------------------------------------------

class TestRestoreFocus:
    """Test _restore_focus() with mocked ctypes."""

    @patch("talkie_modules.text_injector.ctypes")
    def test_hwnd_zero_returns_false(self, mock_ctypes: MagicMock) -> None:
        from talkie_modules.text_injector import _restore_focus
        assert _restore_focus(0) is False

    @patch("talkie_modules.text_injector.ctypes")
    def test_destroyed_window_returns_false(self, mock_ctypes: MagicMock) -> None:
        from talkie_modules.text_injector import _restore_focus
        user32 = mock_ctypes.windll.user32
        user32.IsWindow.return_value = 0
        assert _restore_focus(12345) is False
        user32.IsWindow.assert_called_once_with(12345)

    @patch("talkie_modules.text_injector.time")
    @patch("talkie_modules.text_injector.ctypes")
    def test_attach_thread_input_dance(self, mock_ctypes: MagicMock, mock_time: MagicMock) -> None:
        from talkie_modules.text_injector import _restore_focus
        user32 = mock_ctypes.windll.user32
        kernel32 = mock_ctypes.windll.kernel32
        user32.IsWindow.return_value = 1
        user32.IsIconic.return_value = 0
        kernel32.GetCurrentThreadId.return_value = 100
        user32.GetForegroundWindow.return_value = 9999  # fg window
        user32.GetWindowThreadProcessId.return_value = 300  # fg thread
        user32.SetForegroundWindow.return_value = 1  # success

        assert _restore_focus(42) is True

        # Verify full call sequence using mock_calls
        relevant = [
            c for c in user32.mock_calls
            if c[0] in (
                "AttachThreadInput",
                "SetForegroundWindow", "BringWindowToTop",
            )
        ]
        assert relevant == [
            call.AttachThreadInput(100, 300, True),          # attach to FOREGROUND tid
            call.SetForegroundWindow(42),
            call.BringWindowToTop(42),
            call.AttachThreadInput(100, 300, False),         # detach
        ]

    @patch("talkie_modules.text_injector.time")
    @patch("talkie_modules.text_injector.ctypes")
    def test_detach_happens_on_exception(self, mock_ctypes: MagicMock, mock_time: MagicMock) -> None:
        from talkie_modules.text_injector import _restore_focus
        user32 = mock_ctypes.windll.user32
        kernel32 = mock_ctypes.windll.kernel32
        user32.IsWindow.return_value = 1
        user32.IsIconic.return_value = 0
        kernel32.GetCurrentThreadId.return_value = 100
        user32.GetForegroundWindow.return_value = 9999
        user32.GetWindowThreadProcessId.return_value = 300
        user32.SetForegroundWindow.side_effect = OSError("boom")

        with pytest.raises(OSError):
            _restore_focus(42)

        # Detach must still be called (finally block) — foreground tid, not target
        user32.AttachThreadInput.assert_any_call(100, 300, False)

    @patch("talkie_modules.text_injector.time")
    @patch("talkie_modules.text_injector.ctypes")
    def test_set_foreground_returns_zero(self, mock_ctypes: MagicMock, mock_time: MagicMock) -> None:
        from talkie_modules.text_injector import _restore_focus
        user32 = mock_ctypes.windll.user32
        kernel32 = mock_ctypes.windll.kernel32
        user32.IsWindow.return_value = 1
        user32.IsIconic.return_value = 0
        kernel32.GetCurrentThreadId.return_value = 100
        user32.GetForegroundWindow.return_value = 9999
        user32.GetWindowThreadProcessId.return_value = 300
        user32.SetForegroundWindow.return_value = 0  # failure
        mock_ctypes.GetLastError.return_value = 5

        assert _restore_focus(42) is False

    @patch("talkie_modules.text_injector.time")
    @patch("talkie_modules.text_injector.ctypes")
    def test_minimized_window_gets_restored(self, mock_ctypes: MagicMock, mock_time: MagicMock) -> None:
        from talkie_modules.text_injector import _restore_focus
        user32 = mock_ctypes.windll.user32
        kernel32 = mock_ctypes.windll.kernel32
        user32.IsWindow.return_value = 1
        user32.IsIconic.return_value = 1  # minimized
        kernel32.GetCurrentThreadId.return_value = 100
        user32.GetForegroundWindow.return_value = 9999
        user32.GetWindowThreadProcessId.return_value = 300
        user32.SetForegroundWindow.return_value = 1

        assert _restore_focus(42) is True
        user32.ShowWindow.assert_called_once_with(42, 9)  # SW_RESTORE

    @patch("talkie_modules.text_injector.time")
    @patch("talkie_modules.text_injector.ctypes")
    def test_no_foreground_window_skips_attach(self, mock_ctypes: MagicMock, mock_time: MagicMock) -> None:
        from talkie_modules.text_injector import _restore_focus
        user32 = mock_ctypes.windll.user32
        kernel32 = mock_ctypes.windll.kernel32
        user32.IsWindow.return_value = 1
        user32.IsIconic.return_value = 0
        kernel32.GetCurrentThreadId.return_value = 100
        user32.GetForegroundWindow.return_value = 0  # no foreground window
        user32.SetForegroundWindow.return_value = 1

        assert _restore_focus(42) is True
        # AttachThreadInput should NOT be called when fg_hwnd is 0
        user32.AttachThreadInput.assert_not_called()
        # But SetForegroundWindow should still be attempted
        user32.SetForegroundWindow.assert_called_once_with(42)


# ---------------------------------------------------------------------------
# inject_text tests
# ---------------------------------------------------------------------------

class TestInjectText:
    """Test inject_text() with mocked dependencies."""

    @patch("talkie_modules.text_injector.keyboard")
    @patch("talkie_modules.text_injector.pyperclip")
    def test_empty_text_is_noop(self, mock_clip: MagicMock, mock_kb: MagicMock) -> None:
        from talkie_modules.text_injector import inject_text
        inject_text("")
        mock_clip.copy.assert_not_called()
        mock_kb.send.assert_not_called()

    @patch("talkie_modules.text_injector.keyboard")
    @patch("talkie_modules.text_injector.pyperclip")
    def test_none_text_is_noop(self, mock_clip: MagicMock, mock_kb: MagicMock) -> None:
        from talkie_modules.text_injector import inject_text
        inject_text(None)
        mock_clip.copy.assert_not_called()

    @patch("talkie_modules.text_injector.time")
    @patch("talkie_modules.text_injector.keyboard")
    @patch("talkie_modules.text_injector.pyperclip")
    def test_inject_without_hwnd(self, mock_clip: MagicMock, mock_kb: MagicMock, mock_time: MagicMock) -> None:
        from talkie_modules.text_injector import inject_text
        mock_kb.is_pressed.return_value = False
        inject_text("hello world")
        mock_clip.copy.assert_called_once_with("hello world")
        mock_kb.send.assert_called_once_with("ctrl+v")

    @patch("talkie_modules.text_injector.time")
    @patch("talkie_modules.text_injector._restore_focus", return_value=True)
    @patch("talkie_modules.text_injector.keyboard")
    @patch("talkie_modules.text_injector.pyperclip")
    def test_inject_with_hwnd_restores_focus(
        self, mock_clip: MagicMock, mock_kb: MagicMock,
        mock_restore: MagicMock, mock_time: MagicMock,
    ) -> None:
        from talkie_modules.text_injector import inject_text
        mock_kb.is_pressed.return_value = False
        inject_text("hello", target_hwnd=999)
        mock_restore.assert_called_once_with(999)
        mock_clip.copy.assert_called_once_with("hello")
        mock_kb.send.assert_called_once_with("ctrl+v")

    @patch("talkie_modules.text_injector.time")
    @patch("talkie_modules.text_injector._restore_focus", return_value=False)
    @patch("talkie_modules.text_injector.keyboard")
    @patch("talkie_modules.text_injector.pyperclip")
    def test_inject_fallback_on_restore_failure(
        self, mock_clip: MagicMock, mock_kb: MagicMock,
        mock_restore: MagicMock, mock_time: MagicMock,
    ) -> None:
        """Even if restore fails, text still gets injected to current focus."""
        from talkie_modules.text_injector import inject_text
        mock_kb.is_pressed.return_value = False
        inject_text("fallback text", target_hwnd=888)
        mock_restore.assert_called_once_with(888)
        mock_clip.copy.assert_called_once_with("fallback text")
        mock_kb.send.assert_called_once_with("ctrl+v")


# ---------------------------------------------------------------------------
# Terminal detection + modifier release tests
# ---------------------------------------------------------------------------

class TestTerminalDetection:
    """Test is_terminal_process helper."""

    def test_known_terminal(self) -> None:
        from talkie_modules.text_injector import is_terminal_process
        assert is_terminal_process("warp.exe") is True

    def test_case_insensitive(self) -> None:
        from talkie_modules.text_injector import is_terminal_process
        assert is_terminal_process("WindowsTerminal.exe") is True

    def test_gui_app(self) -> None:
        from talkie_modules.text_injector import is_terminal_process
        assert is_terminal_process("chrome.exe") is False

    def test_empty_string(self) -> None:
        from talkie_modules.text_injector import is_terminal_process
        assert is_terminal_process("") is False


class TestTerminalSanitization:
    """Test control-character sanitization for terminal injection targets."""

    @patch("talkie_modules.text_injector.time")
    @patch("talkie_modules.text_injector.keyboard")
    @patch("talkie_modules.text_injector.pyperclip")
    def test_newlines_replaced_with_spaces(
        self, mock_clip: MagicMock, mock_kb: MagicMock, mock_time: MagicMock,
    ) -> None:
        from talkie_modules.text_injector import inject_text
        mock_kb.is_pressed.return_value = False
        inject_text("hello\nworld", process_name="cmd.exe")
        assert mock_clip.copy.call_args[0][0] == "hello world"

    @patch("talkie_modules.text_injector.time")
    @patch("talkie_modules.text_injector.keyboard")
    @patch("talkie_modules.text_injector.pyperclip")
    def test_crlf_replaced_with_single_space(
        self, mock_clip: MagicMock, mock_kb: MagicMock, mock_time: MagicMock,
    ) -> None:
        """\\r\\n is replaced as a unit — should produce one space, not two."""
        from talkie_modules.text_injector import inject_text
        mock_kb.is_pressed.return_value = False
        inject_text("hello\r\nworld", process_name="cmd.exe")
        assert mock_clip.copy.call_args[0][0] == "hello world"

    @patch("talkie_modules.text_injector.time")
    @patch("talkie_modules.text_injector.keyboard")
    @patch("talkie_modules.text_injector.pyperclip")
    def test_tabs_replaced_with_spaces(
        self, mock_clip: MagicMock, mock_kb: MagicMock, mock_time: MagicMock,
    ) -> None:
        from talkie_modules.text_injector import inject_text
        mock_kb.is_pressed.return_value = False
        inject_text("col1\tcol2", process_name="cmd.exe")
        assert mock_clip.copy.call_args[0][0] == "col1 col2"

    @patch("talkie_modules.text_injector.time")
    @patch("talkie_modules.text_injector.keyboard")
    @patch("talkie_modules.text_injector.pyperclip")
    def test_mixed_control_chars(
        self, mock_clip: MagicMock, mock_kb: MagicMock, mock_time: MagicMock,
    ) -> None:
        from talkie_modules.text_injector import inject_text
        mock_kb.is_pressed.return_value = False
        inject_text("a\r\nb\nc\td", process_name="cmd.exe")
        assert mock_clip.copy.call_args[0][0] == "a b c d"

    @patch("talkie_modules.text_injector.time")
    @patch("talkie_modules.text_injector.keyboard")
    @patch("talkie_modules.text_injector.pyperclip")
    def test_consecutive_newlines_become_multiple_spaces(
        self, mock_clip: MagicMock, mock_kb: MagicMock, mock_time: MagicMock,
    ) -> None:
        """Consecutive newlines each become a space — no collapsing."""
        from talkie_modules.text_injector import inject_text
        mock_kb.is_pressed.return_value = False
        inject_text("a\n\n\nb", process_name="cmd.exe")
        assert mock_clip.copy.call_args[0][0] == "a   b"

    @patch("talkie_modules.text_injector.time")
    @patch("talkie_modules.text_injector.keyboard")
    @patch("talkie_modules.text_injector.pyperclip")
    def test_non_terminal_skips_sanitization(
        self, mock_clip: MagicMock, mock_kb: MagicMock, mock_time: MagicMock,
    ) -> None:
        from talkie_modules.text_injector import inject_text
        mock_kb.is_pressed.return_value = False
        inject_text("hello\nworld", process_name="chrome.exe")
        assert mock_clip.copy.call_args[0][0] == "hello\nworld"

    @patch("talkie_modules.text_injector.time")
    @patch("talkie_modules.text_injector.keyboard")
    @patch("talkie_modules.text_injector.pyperclip")
    def test_sanitization_is_case_insensitive(
        self, mock_clip: MagicMock, mock_kb: MagicMock, mock_time: MagicMock,
    ) -> None:
        from talkie_modules.text_injector import inject_text
        mock_kb.is_pressed.return_value = False
        inject_text("hello\nworld", process_name="PowerShell.exe")
        assert mock_clip.copy.call_args[0][0] == "hello world"

    @patch("talkie_modules.text_injector.time")
    @patch("talkie_modules.text_injector.keyboard")
    @patch("talkie_modules.text_injector.pyperclip")
    def test_sanitization_log_count_accurate(
        self, mock_clip: MagicMock, mock_kb: MagicMock, mock_time: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Logged count must equal actual characters removed, not collapsed spaces."""
        import logging
        from talkie_modules.text_injector import inject_text
        mock_kb.is_pressed.return_value = False
        text = "a\r\nb\nc\td"  # \r\n→" " (removes 1 char), \n→" " (0), \t→" " (0) → net 1 char removed
        with caplog.at_level(logging.INFO, logger="talkie.injector"):
            inject_text(text, process_name="cmd.exe")
        log_line = [r for r in caplog.records if "Sanitized" in r.message]
        assert len(log_line) == 1
        # Original is 8 chars ("a\r\nb\nc\td"), sanitized is "a b c d" (7 chars)
        assert "1 control chars" in log_line[0].message


class TestModifierRelease:
    """Test that stale modifier keys are released before paste."""

    @patch("talkie_modules.text_injector.time")
    @patch("talkie_modules.text_injector.keyboard")
    @patch("talkie_modules.text_injector.pyperclip")
    def test_stale_ctrl_released_before_paste(
        self, mock_clip: MagicMock, mock_kb: MagicMock, mock_time: MagicMock,
    ) -> None:
        from talkie_modules.text_injector import inject_text
        mock_kb.is_pressed.side_effect = lambda k: k == "ctrl"
        inject_text("text")
        mock_kb.release.assert_any_call("ctrl")
        mock_kb.send.assert_called_once_with("ctrl+v")

