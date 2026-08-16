"""Start Menu shortcut management for Talkie."""

import os
import sys

from talkie_modules.logger import get_logger

logger = get_logger("start_menu")

_SHORTCUT_NAME = "Talkie.lnk"


def create_start_menu_shortcut() -> bool:
    """Create the Start Menu shortcut, or repoint a stale one at the current exe.

    No-op in dev mode (non-frozen). Returns True if the shortcut is present
    and targets this exe, or was successfully written.
    """
    if not getattr(sys, "frozen", False):
        logger.debug("Start Menu shortcut only created for the packaged exe")
        return False

    appdata = os.environ.get("APPDATA")
    if not appdata:
        logger.warning("APPDATA not set; cannot create Start Menu shortcut")
        return False

    programs_dir = os.path.join(
        appdata, "Microsoft", "Windows", "Start Menu", "Programs"
    )
    shortcut_path = os.path.join(programs_dir, _SHORTCUT_NAME)

    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        sc = shell.CreateShortcut(shortcut_path)
        # Reconcile a pre-existing shortcut with the current exe path — the
        # portable exe can be moved between launches, same as autostart.
        if os.path.isfile(shortcut_path) and sc.TargetPath == sys.executable:
            return True
        sc.TargetPath = sys.executable
        sc.WorkingDirectory = os.path.dirname(sys.executable)
        sc.IconLocation = sys.executable + ",0"
        sc.Save()
        logger.info("Created Start Menu shortcut: %s", shortcut_path)
        return True
    except ImportError:
        logger.warning("win32com unavailable; skipping Start Menu shortcut")
        return False
    except Exception as e:
        logger.error("Failed to create Start Menu shortcut: %s", e)
        return False
