import keyboard
import threading

class HotkeyManager:
    def __init__(self, hotkey, on_press, on_release):
        """
        hotkey: string like 'alt+space'
        """
        self.hotkey = hotkey.lower()
        self.on_press = on_press
        self.on_release = on_release
        self.is_held = False
        
        parts = self.hotkey.split('+')
        self.trigger_key = parts[-1].strip()
        self.modifiers = [m.strip() for m in parts[:-1]]

    def _on_key_event(self, event):
        # Allow either left or right modifiers, or generic
        all_mods_pressed = all(
            keyboard.is_pressed(mod) or 
            keyboard.is_pressed(f'left {mod}') or 
            keyboard.is_pressed(f'right {mod}') 
            for mod in self.modifiers
        ) if self.modifiers else True
        
        if event.name == self.trigger_key:
            if event.event_type == keyboard.KEY_DOWN:
                if all_mods_pressed and not self.is_held:
                    self.is_held = True
                    if self.on_press:
                        self.on_press()
            elif event.event_type == keyboard.KEY_UP:
                if self.is_held:
                    self.is_held = False
                    if self.on_release:
                        self.on_release()

    def start(self):
        keyboard.hook(self._on_key_event)

    def stop(self):
        keyboard.unhook(self._on_key_event)
