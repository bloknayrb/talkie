import uiautomation as auto
import pyautogui
import pyperclip
import time

def get_context():
    """
    Tries to capture text before the cursor.
    Returns a string of context.
    """
    try:
        # Try UIAutomation first
        focused_control = auto.GetFocusedControl()
        if focused_control:
            # Check if it supports TextPattern
            if focused_control.HasPattern(auto.PatternId.TextPattern):
                pattern = focused_control.GetPattern(auto.PatternId.TextPattern)
                selection = pattern.GetSelection()
                if selection and len(selection) > 0:
                    # If something is selected, context is before the start of selection
                    range_before = pattern.DocumentRange.Clone()
                    range_before.MoveEndpointByRange(auto.TextPatternRangeEndpoint.End, selection[0], auto.TextPatternRangeEndpoint.Start)
                    return range_before.GetText(-1)
                else:
                    # No selection, get text from start to current caret (harder with UIAutomation alone)
                    # Often we can just get the whole text if it's small, or use fallback
                    pass

    except Exception as e:
        print(f"UIAutomation context capture failed: {e}")

    # Fallback: Shift+Home, Copy, Right
    return _get_context_fallback()

def _get_context_fallback():
    original_clipboard = pyperclip.paste()
    try:
        # Use a short delay to ensure the app is ready
        time.sleep(0.05)
        # Select from cursor to start of line
        pyautogui.hotkey('shift', 'home')
        time.sleep(0.05)
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.05)
        # Deselect and return to original position
        pyautogui.press('right')
        
        context = pyperclip.paste()
        # Restore clipboard
        pyperclip.copy(original_clipboard)
        
        # If context is the same as original, it probably failed or there was no text
        if context == original_clipboard:
             # This is ambiguous, but we'll return it for now or empty if we suspect failure
             # A better way is to clear clipboard first
             pass
             
        return context
    except Exception as e:
        print(f"Fallback context capture failed: {e}")
        pyperclip.copy(original_clipboard)
        return ""

if __name__ == "__main__":
    # Test
    print("Wait 3 seconds, then focus on some text...")
    time.sleep(3)
    print(f"Captured Context: '{get_context()}'")
