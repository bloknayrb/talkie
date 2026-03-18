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

    @patch("talkie_modules.text_injector.keyboard")
    @patch("talkie_modules.text_injector.pyperclip")
    def test_inject_without_hwnd(self, mock_clip: MagicMock, mock_kb: MagicMock) -> None:
        from talkie_modules.text_injector import inject_text
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
        inject_text("hello", target_hwnd=999)
        mock_restore.assert_called_once_with(999)
        mock_time.sleep.assert_called_once_with(0.075)
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
        inject_text("fallback text", target_hwnd=888)
        mock_restore.assert_called_once_with(888)
        # Still sleeps and injects
        mock_time.sleep.assert_called_once_with(0.075)
        mock_clip.copy.assert_called_once_with("fallback text")
        mock_kb.send.assert_called_once_with("ctrl+v")


# ---------------------------------------------------------------------------
# get_target_hwnd tests
# ---------------------------------------------------------------------------

class TestGetTargetHwnd:
    """Test get_target_hwnd() with mocked ctypes."""

    @patch("talkie_modules.context_capture.ctypes")
    def test_returns_hwnd(self, mock_ctypes: MagicMock) -> None:
        from talkie_modules.context_capture import get_target_hwnd
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = 42
        mock_ctypes.create_unicode_buffer.return_value = MagicMock(value="Notepad")
        assert get_target_hwnd() == 42

    @patch("talkie_modules.context_capture.ctypes")
    def test_returns_zero_on_null(self, mock_ctypes: MagicMock) -> None:
        from talkie_modules.context_capture import get_target_hwnd
        mock_ctypes.windll.user32.GetForegroundWindow.return_value = 0
        assert get_target_hwnd() == 0

    @patch("talkie_modules.context_capture.ctypes")
    def test_returns_zero_on_exception(self, mock_ctypes: MagicMock) -> None:
        from talkie_modules.context_capture import get_target_hwnd
        mock_ctypes.windll.user32.GetForegroundWindow.side_effect = OSError("fail")
        assert get_target_hwnd() == 0
