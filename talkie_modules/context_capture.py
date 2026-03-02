"""Capture text context around the cursor for Talkie."""

import time
from typing import Optional

import pyautogui
import pyperclip
import uiautomation as auto

from talkie_modules.logger import get_logger

logger = get_logger("context")


def get_context() -> str:
    """
    Capture text before the cursor using UIAutomation, falling back to clipboard.
    Returns captured context string (may be empty).
    """
    try:
        focused_control = auto.GetFocusedControl()
        if focused_control:
            if focused_control.HasPattern(auto.PatternId.TextPattern):
                pattern = focused_control.GetPattern(auto.PatternId.TextPattern)
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

    return _get_context_fallback()


def _get_context_fallback() -> str:
    """Fallback: select line via Shift+Home, copy, restore cursor."""
    original_clipboard: str = pyperclip.paste()
    try:
        time.sleep(0.05)
        pyautogui.hotkey("shift", "home")
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.05)
        pyautogui.press("right")

        context: str = pyperclip.paste()
        pyperclip.copy(original_clipboard)

        if context == original_clipboard:
            # Ambiguous — clipboard didn't change, may have failed
            logger.debug("Fallback context same as original clipboard")

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
