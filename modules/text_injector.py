import pyperclip
import pyautogui
import time

def inject_text(text):
    """
    Injects text into the active application by pasting.
    """
    if not text:
        return

    # Save current clipboard
    old_clipboard = pyperclip.paste()
    
    # Put new text in clipboard
    pyperclip.copy(text)
    
    # Simulate paste
    pyautogui.hotkey('ctrl', 'v')
    
    # Wait for the paste to complete
    time.sleep(0.15)
    
    # Restore original clipboard
    pyperclip.copy(old_clipboard)

if __name__ == "__main__":
    # Test
    print("Wait 3 seconds, then focus on some text field...")
    time.sleep(3)
    inject_text("Hello, this is a test injection.")
