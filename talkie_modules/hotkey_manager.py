"""Global hotkey listener for Talkie."""

import threading
from typing import Callable, Optional

import keyboard

from talkie_modules.logger import get_logger

logger = get_logger("hotkey")


class HotkeyManager:
    """Listens for a configurable hold-to-talk hotkey.

    Uses per-key suppression via ``keyboard.hook_key`` so that only the
    trigger key's scan-codes are intercepted.  All other keys (including
    synthetic Ctrl+V from pyautogui) pass through untouched.
    """

    def __init__(
        self,
        hotkey: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ) -> None:
        self.hotkey: str = hotkey.lower()
        self.on_press: Callable[[], None] = on_press
        self.on_release: Callable[[], None] = on_release
        self.is_held: bool = False
        self._hook_handle: Optional[object] = None

        parts = self.hotkey.split("+")
        self.trigger_key: str = parts[-1].strip()
        self.modifiers: list[str] = [m.strip() for m in parts[:-1]]

    @staticmethod
    def _matches_key(event_name: str, key: str) -> bool:
        """Check if event_name matches key, including left/right variants."""
        return event_name in (key, f"left {key}", f"right {key}")

    def _on_trigger_key(self, event: keyboard.KeyboardEvent) -> Optional[bool]:
        """Handle trigger key events.  Runs in the hook thread (synchronous).

        Returns ``False`` to suppress the event, ``True`` to pass through.
        Because we registered via ``hook_key``, this callback is only
        invoked for the trigger key's scan-codes — other keys are never
        affected.
        """
        all_mods_pressed: bool = all(
            keyboard.is_pressed(mod)
            or keyboard.is_pressed(f"left {mod}")
            or keyboard.is_pressed(f"right {mod}")
            for mod in self.modifiers
        ) if self.modifiers else True

        if event.event_type == keyboard.KEY_DOWN:
            if all_mods_pressed and not self.is_held:
                self.is_held = True
                logger.info("Hotkey pressed: %s", self.hotkey)
                if self.on_press:
                    # Dispatch to thread — hook thread has ~300ms Windows timeout
                    threading.Thread(target=self.on_press, daemon=True).start()
            # Suppress trigger key while modifiers held to prevent
            # OS side effects (e.g. Windows key opening Start Menu)
            if all_mods_pressed:
                return False
        elif event.event_type == keyboard.KEY_UP:
            if self.is_held:
                self.is_held = False
                logger.info("Hotkey released: %s", self.hotkey)
                if self.on_release:
                    threading.Thread(target=self.on_release, daemon=True).start()
                return False
        return True

    def start(self) -> None:
        """Start listening for the hotkey."""
        self._hook_handle = keyboard.hook_key(
            self.trigger_key, self._on_trigger_key, suppress=True
        )
        logger.info("Hotkey listener started: %s", self.hotkey)

    def stop(self) -> None:
        """Stop listening for the hotkey."""
        try:
            if self._hook_handle:
                keyboard.unhook_key(self._hook_handle)
            logger.info("Hotkey listener stopped")
        except (KeyError, ValueError):
            logger.debug("Hotkey was not hooked or already unhooked")
