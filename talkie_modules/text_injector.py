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

# Terminals and TUI-hosting apps where synthetic Ctrl+V disrupts the running
# process (e.g. Claude Code's Ink TUI interprets ^V as a control character
# instead of Warp/WT handling it as a clipboard paste).
_TERMINAL_PROCESSES = frozenset({
    "warp.exe",
    "windowsterminal.exe",
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "conhost.exe",
    "alacritty.exe",
    "wezterm-gui.exe",
    "hyper.exe",
    "mintty.exe",
})

# Subset of terminals that intercept Ctrl+Shift+V as paste at the emulator
# layer (never reaching the PTY). These also support modern keyboard protocols
# that send raw modifier events as escape sequences in raw mode, so we skip
# the synthetic modifier pre-release for them.
# Legacy Windows console hosts (cmd, conhost, powershell) use Ctrl+V for paste
# and do NOT belong here.
_RICHTERM_PROCESSES = frozenset({
    "warp.exe",
    "windowsterminal.exe",
    "alacritty.exe",
    "wezterm-gui.exe",
    "hyper.exe",
    "mintty.exe",
})


def is_terminal_process(process_name: str) -> bool:
    """Check whether a process name belongs to a known terminal emulator."""
    return process_name.lower() in _TERMINAL_PROCESSES


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

    # If the target already has focus, skip refocus entirely — calling
    # SetForegroundWindow on an already-focused window can cause some apps
    # (browsers, Electron, WinUI) to auto-select all text in the active field,
    # which would make the subsequent Ctrl+V replace everything.
    fg_hwnd = user32.GetForegroundWindow()
    if fg_hwnd == hwnd:
        logger.debug("Target HWND=%d already has focus, skipping refocus", hwnd)
        return True

    current_tid = kernel32.GetCurrentThreadId()
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


def inject_text(text: Optional[str], target_hwnd: int = 0, process_name: str = "") -> None:
    """Paste text into the focused application via clipboard.

    If target_hwnd is provided, attempt to restore focus to that window first.
    On failure, falls through to inject at whatever window currently has focus.

    Terminal targets use Ctrl+Shift+V (handled by the terminal emulator, not
    passed to the PTY) to avoid disrupting TUI apps like Claude Code.
    """
    if not text:
        logger.debug("Nothing to inject (empty text)")
        return

    # Sanitize text for terminal targets: strip control characters that could
    # be interpreted as commands (newlines execute, tabs may trigger completion).
    if process_name.lower() in _TERMINAL_PROCESSES:
        sanitized = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").replace("\t", " ")
        if sanitized != text:
            logger.info("Sanitized %d control chars for terminal target %s",
                        len(text) - len(sanitized), process_name)
        text = sanitized

    # Copy to clipboard BEFORE restoring focus. Some apps (Electron, browsers,
    # editors) cache the clipboard at focus-gain time. If we copy after, the app
    # sees the previous clipboard entry and pastes that instead of the new text.
    pyperclip.copy(text)

    if target_hwnd:
        restored = _restore_focus(target_hwnd)
        # Sleep unconditionally — even failed restore may have partially shifted focus
        time.sleep(_FOCUS_RESTORE_DELAY)
        if restored:
            logger.debug("Restored focus to HWND=%d before injection", target_hwnd)
        else:
            logger.info("Focus restore failed for HWND=%d, injecting to current focus", target_hwnd)

    if process_name.lower() in _RICHTERM_PROCESSES:
        # Modern terminal emulators (Warp, Windows Terminal, Alacritty, etc.)
        # intercept Ctrl+Shift+V at the emulator layer, never passing it to the
        # PTY. This avoids delivering ^V (0x16) to TUI apps like Claude Code's
        # Ink that run in raw mode and interpret ^V as a control character.
        # We also skip the modifier pre-release: these terminals implement
        # modern keyboard protocols that translate raw modifier events into
        # escape sequences in raw mode, so a synthetic ctrl-up can disrupt TUI.
        keyboard.send("ctrl+shift+v")
    else:
        # Defensive: release any stale modifier keys before sending synthetic
        # paste. The hotkey combo (e.g. Ctrl+Win) may leave Ctrl in a held
        # state if the user's release timing is slightly off.
        for mod in ("ctrl", "shift", "alt"):
            try:
                if keyboard.is_pressed(mod):
                    keyboard.release(mod)
            except Exception:
                pass
        time.sleep(0.03)
        keyboard.send("ctrl+v")
    logger.info("Injected %d chars", len(text))


if __name__ == "__main__":
    print("Wait 3 seconds, then focus on some text field...")
    time.sleep(3)
    inject_text("Hello, this is a test injection.")
