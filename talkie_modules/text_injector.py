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
_VK_MENU = 0x12
_KEYEVENTF_EXTENDEDKEY = 0x0001
_KEYEVENTF_KEYUP = 0x0002


def _restore_focus(hwnd: int) -> bool:
    """Restore foreground focus to the given HWND.

    Uses the keybd_event Alt trick to acquire the foreground lock from a
    background thread, then AttachThreadInput to the *foreground* thread
    (not the target) to borrow its lock before calling SetForegroundWindow.

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

    # Alt key trick: synthetic Alt press/release acquires the foreground lock
    # for our process even from a background thread. This is the canonical
    # pattern used by AutoHotkey/AutoIt for 20+ years.
    user32.keybd_event(_VK_MENU, 0, _KEYEVENTF_EXTENDEDKEY, 0)
    user32.keybd_event(_VK_MENU, 0, _KEYEVENTF_EXTENDEDKEY | _KEYEVENTF_KEYUP, 0)

    # Brief yield to let the foreground lock transfer complete
    time.sleep(0.01)

    # Attach to the foreground thread to borrow its input queue
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
