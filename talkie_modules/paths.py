"""Single source of truth for all path resolution in Talkie."""

import os
import sys
from typing import Final


def get_base_dir() -> str:
    """Return the application base directory, handling both frozen (PyInstaller) and dev modes."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR: Final[str] = get_base_dir()
ASSETS_DIR: Final[str] = os.path.join(BASE_DIR, 'assets')
CONFIG_FILE: Final[str] = os.path.join(BASE_DIR, 'config.json')
LOG_FILE: Final[str] = os.path.join(BASE_DIR, 'talkie.log')
