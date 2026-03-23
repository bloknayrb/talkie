"""Dictation history — stores recent transcriptions with metadata.

Entries are stored in DATA_DIR/history.json, capped at MAX_ENTRIES.
Thread-safe via a module-level lock. Atomic writes prevent corruption.
"""

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from talkie_modules.logger import get_logger
from talkie_modules.paths import DATA_DIR

logger = get_logger("history")

HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
MAX_ENTRIES = 200

_lock = threading.Lock()


def _read() -> list[dict[str, Any]]:
    """Read history entries from disk. Returns empty list on any error."""
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("entries", [])
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("Corrupt history file, starting fresh: %s", e)
        return []


def _write(entries: list[dict[str, Any]]) -> None:
    """Atomically write entries to disk (temp file + replace)."""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=os.path.dirname(HISTORY_FILE), suffix=".tmp",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump({"entries": entries}, f, indent=2)
        os.replace(tmp_path, HISTORY_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def add_entry(
    text: str,
    target_app: str = "",
    target_title: str = "",
    duration: float = 0.0,
) -> dict[str, Any]:
    """Append a history entry. Prunes oldest if over MAX_ENTRIES. Returns the new entry."""
    entry = {
        "id": uuid.uuid4().hex[:8],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "text": text,
        "target_app": target_app,
        "target_title": target_title,
        "duration": round(duration, 1),
    }
    with _lock:
        entries = _read()
        entries.append(entry)
        if len(entries) > MAX_ENTRIES:
            entries = entries[-MAX_ENTRIES:]
        _write(entries)
    logger.debug("History entry added: %s (%d chars)", entry["id"], len(text))
    return entry


def get_entries(limit: Optional[int] = None) -> list[dict[str, Any]]:
    """Return entries newest-first. Optional limit."""
    with _lock:
        entries = _read()
    if limit is not None and limit > 0:
        entries = entries[-limit:]
    entries.reverse()
    return entries


def get_entry(entry_id: str) -> Optional[dict[str, Any]]:
    """Look up a single entry by id."""
    with _lock:
        entries = _read()
    return next((e for e in entries if e["id"] == entry_id), None)


def delete_entry(entry_id: str) -> bool:
    """Remove a single entry. Returns True if found and deleted."""
    with _lock:
        entries = _read()
        before = len(entries)
        entries = [e for e in entries if e["id"] != entry_id]
        if len(entries) == before:
            return False
        _write(entries)
    return True


def clear() -> None:
    """Delete all history entries."""
    with _lock:
        _write([])
    logger.info("History cleared")
