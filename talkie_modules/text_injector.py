"""Inject processed text into the active application via clipboard paste."""

import time
from typing import Optional

import pyautogui
import pyperclip

from talkie_modules.logger import get_logger

logger = get_logger("injector")


def inject_text(text: Optional[str]) -> None:
    """Paste text into the focused application via clipboard."""
    if not text:
        logger.debug("Nothing to inject (empty text)")
        return

    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")
    logger.info("Injected %d chars", len(text))


if __name__ == "__main__":
    print("Wait 3 seconds, then focus on some text field...")
    time.sleep(3)
    inject_text("Hello, this is a test injection.")
