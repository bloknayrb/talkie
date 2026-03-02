"""Global hotkey listener for Talkie."""

from typing import Callable, Optional

import keyboard

from talkie_modules.logger import get_logger

logger = get_logger("hotkey")


class HotkeyManager:
    """Listens for a configurable hold-to-talk hotkey."""

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

        parts = self.hotkey.split("+")
        self.trigger_key: str = parts[-1].strip()
        self.modifiers: list[str] = [m.strip() for m in parts[:-1]]

    def _on_key_event(self, event: keyboard.KeyboardEvent) -> None:
        all_mods_pressed: bool = all(
            keyboard.is_pressed(mod)
            or keyboard.is_pressed(f"left {mod}")
            or keyboard.is_pressed(f"right {mod}")
            for mod in self.modifiers
        ) if self.modifiers else True

        if event.name == self.trigger_key:
            if event.event_type == keyboard.KEY_DOWN:
                if all_mods_pressed and not self.is_held:
                    self.is_held = True
                    logger.debug("Hotkey pressed: %s", self.hotkey)
                    if self.on_press:
                        self.on_press()
            elif event.event_type == keyboard.KEY_UP:
                if self.is_held:
                    self.is_held = False
                    logger.debug("Hotkey released: %s", self.hotkey)
                    if self.on_release:
                        self.on_release()

    def start(self) -> None:
        """Start listening for the hotkey."""
        keyboard.hook(self._on_key_event)
        logger.info("Hotkey listener started: %s", self.hotkey)

    def stop(self) -> None:
        """Stop listening for the hotkey."""
        try:
            keyboard.unhook(self._on_key_event)
            logger.info("Hotkey listener stopped")
        except (KeyError, ValueError):
            logger.debug("Hotkey was not hooked or already unhooked")
