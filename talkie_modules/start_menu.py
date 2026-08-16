"""Start Menu shortcut management for Talkie."""

import os
import sys
import threading

from talkie_modules.logger import get_logger

logger = get_logger("start_menu")

_SHORTCUT_NAME = "Talkie.lnk"


def _same_path(a: str, b: str) -> bool:
    """Compare two Windows paths case-insensitively, resolving 8.3 short names.

    Shell resolves a .lnk's TargetPath through IShellLinkW, which may hand back
    a different case or the short (8.3) form of the path we originally wrote, so
    a plain `==` would report drift on every launch.
    """
    try:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(
            os.path.realpath(b)
        )
    except OSError:
        return os.path.normcase(a) == os.path.normcase(b)


def create_start_menu_shortcut() -> bool:
    """Create the Start Menu shortcut, or reconcile a stale one with this exe.

    No-op in dev mode (non-frozen). Returns True if the shortcut already matches
    this exe, or was successfully written.
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
        import pythoncom
        import win32com.client
    except ImportError:
        logger.warning("win32com unavailable; skipping Start Menu shortcut")
        return False

    target = sys.executable
    working_dir = os.path.dirname(sys.executable)
    icon = sys.executable + ",0"

    # COM apartments are per-thread, and this runs on a worker thread, so the
    # main thread's initialization does not carry over.
    com_ready = False
    try:
        pythoncom.CoInitialize()
        com_ready = True
    except Exception as e:
        # Already initialized under an incompatible apartment model; Dispatch
        # still works on the existing one.
        logger.debug("CoInitialize skipped: %s", e)

    try:
        os.makedirs(programs_dir, exist_ok=True)
        shell = win32com.client.Dispatch("WScript.Shell")
        existed = os.path.isfile(shortcut_path)
        try:
            sc = shell.CreateShortcut(shortcut_path)
        except Exception as e:
            # A corrupt or non-.lnk file at this path would otherwise wedge us
            # into failing here on every launch. Discard it and start clean.
            if not existed:
                raise
            logger.warning("Discarding unreadable Start Menu shortcut: %s", e)
            os.remove(shortcut_path)
            existed = False
            sc = shell.CreateShortcut(shortcut_path)

        # Reconcile every property, not just the target — the portable exe can
        # move between launches, and a shortcut written by an older build may
        # point at the right exe with a stale working dir or icon.
        if (
            existed
            and _same_path(sc.TargetPath, target)
            and _same_path(sc.WorkingDirectory, working_dir)
            and os.path.normcase(sc.IconLocation) == os.path.normcase(icon)
        ):
            return True

        sc.TargetPath = target
        sc.WorkingDirectory = working_dir
        sc.IconLocation = icon
        sc.Save()
        logger.info(
            "%s Start Menu shortcut: %s",
            "Updated" if existed else "Created",
            shortcut_path,
        )
        return True
    except Exception as e:
        logger.error("Failed to create Start Menu shortcut: %s", e)
        return False
    finally:
        if com_ready:
            pythoncom.CoUninitialize()


def create_start_menu_shortcut_async() -> threading.Thread:
    """Reconcile the shortcut on a worker thread, off the startup path.

    Dispatch/Save are normally instant, but they are out-of-process COM calls
    with no timeout available to us. Running them inline would put a hung
    WScript.Shell — a broken registration, an AV shim — between launch and the
    hotkey listener and tray icon. The thread is a daemon, so a hang delays
    nothing and does not keep the process alive at exit.
    """
    thread = threading.Thread(
        target=create_start_menu_shortcut,
        name="start-menu-shortcut",
        daemon=True,
    )
    thread.start()
    return thread
