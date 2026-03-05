"""Single source of truth for all path resolution in Talkie."""

import os
import sys
from typing import Final


def _get_bundle_dir() -> str:
    """Return the directory where PyInstaller extracted bundled data files."""
    return getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_base_dir() -> str:
    """Return the application base directory (next to the .exe, or repo root in dev)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR: Final[str] = get_base_dir()
_BUNDLE_DIR: Final[str] = _get_bundle_dir()
ASSETS_DIR: Final[str] = os.path.join(_BUNDLE_DIR, 'assets')
CONFIG_FILE: Final[str] = os.path.join(BASE_DIR, 'config.json')
LOG_FILE: Final[str] = os.path.join(BASE_DIR, 'talkie.log')
