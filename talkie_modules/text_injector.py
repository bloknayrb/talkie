"""Inject processed text into the active application via clipboard paste."""

import ctypes
import ctypes.wintypes
import time
from typing import Optional

import keyboard
import pyperclip

from talkie_modules.logger import get_logger

logger = get_logger("injector")

# Delay after focus restore to let the target window activate (ms → seconds)
_FOCUS_RESTORE_DELAY = 0.075

# Win32 constants for _restore_focus
_SW_RESTORE = 9


def _restore_focus(hwnd: int) -> bool:
    """Restore foreground focus to the given HWND.

    Uses AttachThreadInput to borrow the foreground thread's input queue,
    then calls SetForegroundWindow.

    Returns True on success, False on failure (graceful fallback).
    """
    if not hwnd:
        return False

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # Pre-flight: target window still exists?
    if not user32.IsWindow(hwnd):
        logger.info("Target window (HWND=%d) no longer exists, injecting to current focus", hwnd)
        return False

    # Restore minimized windows before attempting focus
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, _SW_RESTORE)
        time.sleep(0.015)  # Let restore animation settle

    current_tid = kernel32.GetCurrentThreadId()

    # Get the FOREGROUND window's thread (the one holding the lock) — NOT the target's
    fg_hwnd = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0

    # Attach to the foreground thread to borrow its input queue, which allows
    # SetForegroundWindow to succeed from a background thread.
    #
    # NOTE: The old Alt key trick (keybd_event VK_MENU press/release) was removed
    # because WinUI 3 apps (e.g. Windows 11 Notepad) interpret the synthetic Alt
    # tap as real and show access-key hint overlays on the UI.
    attached = False
    if fg_tid and fg_tid != current_tid:
        user32.AttachThreadInput(current_tid, fg_tid, True)
        attached = True

    try:
        result = user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        if not result:
            last_error = ctypes.GetLastError()
            logger.info(
                "SetForegroundWindow returned 0 for HWND=%d (LastError=%d), "
                "injecting to current focus", hwnd, last_error,
            )
            return False
        return True
    finally:
        if attached:
            user32.AttachThreadInput(current_tid, fg_tid, False)


def inject_text(text: Optional[str], target_hwnd: int = 0) -> None:
    """Paste text into the focused application via clipboard.

    If target_hwnd is provided, attempt to restore focus to that window first.
    On failure, falls through to inject at whatever window currently has focus.
    """
    if not text:
        logger.debug("Nothing to inject (empty text)")
        return

    if target_hwnd:
        restored = _restore_focus(target_hwnd)
        # Sleep unconditionally — even failed restore may have partially shifted focus
        time.sleep(_FOCUS_RESTORE_DELAY)
        if restored:
            logger.debug("Restored focus to HWND=%d before injection", target_hwnd)
        else:
            logger.info("Focus restore failed for HWND=%d, injecting to current focus", target_hwnd)

    pyperclip.copy(text)
    keyboard.send("ctrl+v")
    logger.info("Injected %d chars", len(text))


if __name__ == "__main__":
    print("Wait 3 seconds, then focus on some text field...")
    time.sleep(3)
    inject_text("Hello, this is a test injection.")
