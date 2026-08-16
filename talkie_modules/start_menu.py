"""Start Menu shortcut management for Talkie."""

import os
import sys

from talkie_modules.logger import get_logger

logger = get_logger("start_menu")

_SHORTCUT_NAME = "Talkie.lnk"


def create_start_menu_shortcut() -> bool:
    """Create a Start Menu shortcut for Talkie if one doesn't already exist.

    No-op in dev mode (non-frozen). Returns True if the shortcut exists
    or was successfully created.
    """
    if not getattr(sys, "frozen", False):
        logger.debug("Start Menu shortcut only created for the packaged exe")
        return False

    programs_dir = os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft", "Windows", "Start Menu", "Programs",
    )
    if not programs_dir:
        logger.warning("APPDATA not set; cannot create Start Menu shortcut")
        return False

    shortcut_path = os.path.join(programs_dir, _SHORTCUT_NAME)
    if os.path.isfile(shortcut_path):
        return True

    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        sc = shell.CreateShortcut(shortcut_path)
        sc.TargetPath = sys.executable
        sc.WorkingDirectory = os.path.dirname(sys.executable)
        sc.IconLocation = os.path.join(sys.executable, ",0")
        sc.Save()
        logger.info("Created Start Menu shortcut: %s", shortcut_path)
        return True
    except ImportError:
        logger.warning("win32com unavailable; skipping Start Menu shortcut")
        return False
    except Exception as e:
        logger.error("Failed to create Start Menu shortcut: %s", e)
        return False
