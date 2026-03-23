"""Windows autostart registry management for Talkie."""

import sys
import winreg

from talkie_modules.logger import get_logger

logger = get_logger("autostart")

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "Talkie"


def is_autostart_enabled() -> bool:
    """Check if Talkie is registered to start on boot with the current exe path."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
            expected = f'"{sys.executable}"'
            return value == expected
    except FileNotFoundError:
        return False
    except OSError as e:
        logger.error("Failed to read autostart registry: %s", e)
        return False


def enable_autostart() -> bool:
    """Register Talkie to start on boot. No-op in dev mode."""
    if not getattr(sys, "frozen", False):
        logger.warning("Autostart only works with the packaged exe, skipping")
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, f'"{sys.executable}"')
        logger.info("Autostart enabled: %s", sys.executable)
        return True
    except OSError as e:
        logger.error("Failed to enable autostart: %s", e)
        return False


def disable_autostart() -> bool:
    """Remove Talkie from autostart. Idempotent — returns True if already absent."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, _VALUE_NAME)
        logger.info("Autostart disabled")
        return True
    except FileNotFoundError:
        return True
    except OSError as e:
        logger.error("Failed to disable autostart: %s", e)
        return False


def sync_autostart(enabled: bool) -> bool:
    """Enable or disable autostart based on the config value. Returns success."""
    return enable_autostart() if enabled else disable_autostart()
