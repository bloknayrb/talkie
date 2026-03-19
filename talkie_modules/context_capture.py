"""Capture text context around the cursor for Talkie."""

import ctypes
import ctypes.wintypes
import os
import time

import pyautogui
import pyperclip
import uiautomation as auto

from talkie_modules.logger import get_logger

logger = get_logger("context")

# Win32 constants for process querying
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def get_target_window() -> tuple[int, str, str]:
    """Return (hwnd, process_name, window_title) for the current foreground window.

    Called at hotkey press time. Falls back gracefully: if process name
    detection fails (e.g. elevated process), returns empty string for
    process_name so title matching still works.
    """
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return (0, "", "")

        # Get window title
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
        window_title = buf.value

        # Get process name from HWND
        process_name = ""
        pid = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            handle = ctypes.windll.kernel32.OpenProcess(
                _PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
            )
            if handle:
                try:
                    exe_buf = ctypes.create_unicode_buffer(260)
                    size = ctypes.wintypes.DWORD(260)
                    if ctypes.windll.kernel32.QueryFullProcessImageNameW(
                        handle, 0, exe_buf, ctypes.byref(size)
                    ):
                        process_name = os.path.basename(exe_buf.value)
                finally:
                    ctypes.windll.kernel32.CloseHandle(handle)

        logger.debug(
            "Captured target HWND=%d process=%r title=%r",
            hwnd, process_name, window_title,
        )
        return (hwnd, process_name, window_title)
    except Exception as e:
        logger.warning("get_target_window failed: %s", e)
        return (0, "", "")


def get_context(use_fallback: bool = True) -> str:
    """
    Capture text before the cursor using UIAutomation, falling back to clipboard.

    Args:
        use_fallback: If True (default), fall back to keyboard-based capture when
            UIAutomation fails. Set to False when modifier keys are held (e.g. during
            hotkey press) to avoid synthetic keystroke conflicts.

    Returns captured context string (may be empty).
    """
    try:
        with auto.UIAutomationInitializerInThread():
            focused_control = auto.GetFocusedControl()
            if focused_control:
                pattern = focused_control.GetPattern(auto.PatternId.TextPattern)
                if pattern:
                    selection = pattern.GetSelection()
                    if selection and len(selection) > 0:
                        range_before = pattern.DocumentRange.Clone()
                        range_before.MoveEndpointByRange(
                            auto.TextPatternRangeEndpoint.End,
                            selection[0],
                            auto.TextPatternRangeEndpoint.Start,
                        )
                        context = range_before.GetText(-1)
                        logger.debug("UIAutomation captured %d chars", len(context))
                        return context
    except Exception as e:
        logger.warning("UIAutomation context capture failed: %s", e)

    if use_fallback:
        return _get_context_fallback()
    logger.debug("Skipping keyboard fallback (modifiers held)")
    return ""


def _get_context_fallback() -> str:
    """Fallback: select line via Shift+Home, copy, restore cursor."""
    original_clipboard: str = pyperclip.paste()
    seq_before = ctypes.windll.user32.GetClipboardSequenceNumber()
    try:
        time.sleep(0.05)
        pyautogui.hotkey("shift", "home")
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.05)
        pyautogui.press("right")

        context: str = pyperclip.paste()

        seq_after = ctypes.windll.user32.GetClipboardSequenceNumber()
        if seq_after - seq_before > 1:
            # Clipboard changed by something other than our Ctrl+C — don't clobber
            logger.debug("Clipboard changed externally during fallback — skipping restore")
            return ""

        pyperclip.copy(original_clipboard)

        if context == original_clipboard:
            # Clipboard didn't change — copy failed (e.g. modifier keys held)
            logger.debug("Fallback context same as original clipboard — treating as no context")
            return ""

        logger.debug("Fallback captured %d chars", len(context))
        return context
    except Exception as e:
        logger.warning("Fallback context capture failed: %s", e)
        pyperclip.copy(original_clipboard)
        return ""


if __name__ == "__main__":
    print("Wait 3 seconds, then focus on some text...")
    time.sleep(3)
    print(f"Captured Context: '{get_context()}'")
