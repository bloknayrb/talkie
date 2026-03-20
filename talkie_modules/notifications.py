"""Error notification system for Talkie — toast notifications and error chimes."""

import winsound

from talkie_modules.logger import get_logger

logger = get_logger("notify")

# Try to import winotify for toast notifications; fall back to chime-only
_HAS_WINOTIFY = False
try:
    from winotify import Notification, audio
    _HAS_WINOTIFY = True
except ImportError:
    logger.debug("winotify not installed — using system chime for error notifications")


def play_error_chime() -> None:
    """Play a system error chime (non-blocking)."""
    try:
        winsound.MessageBeep(winsound.MB_ICONHAND)
    except Exception as e:
        logger.debug("Could not play error chime: %s", e)


def show_toast(title: str, message: str, duration: str = "short") -> None:
    """
    Show a Windows toast notification if winotify is available.
    Falls back to logging if not.
    """
    if _HAS_WINOTIFY:
        try:
            toast = Notification(
                app_id="Talkie",
                title=title,
                msg=message,
                duration=duration,
            )
            toast.set_audio(audio.Default, loop=False)
            toast.show()
            logger.debug("Toast shown: %s — %s", title, message)
        except Exception as e:
            logger.warning("Toast notification failed: %s", e)
    else:
        logger.info("Notification: %s — %s", title, message)


def play_discard_chime() -> None:
    """Play a subtle notification chime for discarded recordings (non-blocking)."""
    try:
        winsound.MessageBeep(winsound.MB_OK)
    except Exception as e:
        logger.debug("Could not play discard chime: %s", e)


def notify_discard(reason: str) -> None:
    """Play discard chime and show toast for discarded recordings."""
    play_discard_chime()
    show_toast("Talkie", reason)


def notify_error(message: str) -> None:
    """Play error chime and show toast notification for pipeline errors."""
    play_error_chime()
    show_toast("Talkie Error", message)


def play_clipboard_chime() -> None:
    """Play a subtle chime indicating text was copied to clipboard (non-blocking)."""
    try:
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception as e:
        logger.debug("Could not play clipboard chime: %s", e)


def notify_clipboard_ready() -> None:
    """Notify user that dictated text is on the clipboard, ready to paste."""
    play_clipboard_chime()
    show_toast("Talkie", "Text copied to clipboard — paste with Ctrl+V")
