"""In-app update checker and installer for Talkie.

Checks GitHub Releases for new versions, downloads the updated exe,
and spawns a .cmd script to swap the running binary on Windows.
Uses only stdlib — no additional dependencies.
"""

import json
import logging
import os
import subprocess
import sys
import urllib.error
import urllib.request

logger = logging.getLogger("talkie.updater")

GITHUB_API_URL = "https://api.github.com/repos/bloknayrb/talkie/releases/latest"
_USER_AGENT = "Talkie-Updater/1.0"


def compare_versions(current: str, latest: str) -> bool:
    """Return True if *latest* is newer than *current*."""
    def _parse(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    try:
        return _parse(latest) > _parse(current)
    except (ValueError, TypeError):
        return False


def check_for_update(current_version: str) -> dict:
    """Query GitHub Releases and return update info.

    Returns a dict with keys: available, latest_version, download_url,
    download_size, release_notes, error.
    """
    try:
        req = urllib.request.Request(GITHUB_API_URL, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            return {"available": False, "error": "GitHub API rate limit reached. Try again in a few minutes."}
        return {"available": False, "error": f"GitHub API error (HTTP {exc.code})"}
    except (urllib.error.URLError, OSError):
        return {"available": False, "error": "Could not reach GitHub. Check your internet connection."}

    tag = data.get("tag_name", "")
    if not compare_versions(current_version, tag):
        return {"available": False, "latest_version": tag.lstrip("v")}

    # Find the .exe asset
    download_url = ""
    download_size = 0
    for asset in data.get("assets", []):
        if asset.get("name", "").lower().endswith(".exe"):
            download_url = asset["browser_download_url"]
            download_size = asset.get("size", 0)
            break

    if not download_url:
        return {"available": False, "error": "No .exe found in the latest release."}

    return {
        "available": True,
        "latest_version": tag.lstrip("v"),
        "download_url": download_url,
        "download_size": download_size,
        "release_notes": data.get("body", ""),
    }


def download_update(url: str, dest_path: str, expected_size: int,
                    progress_callback=None) -> None:
    """Download the update exe to *dest_path*.

    Downloads to a .tmp file first, validates size, then renames.
    Calls progress_callback(bytes_downloaded, total_bytes) during download.
    """
    tmp_path = dest_path + ".tmp"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0)) or expected_size
            downloaded = 0

            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)

        # Validate file size if we have a reference
        actual_size = os.path.getsize(tmp_path)
        if expected_size and actual_size != expected_size:
            raise OSError(
                f"Downloaded file size ({actual_size}) doesn't match "
                f"expected size ({expected_size})"
            )

        # Atomic-ish rename: remove dest if it exists, then rename tmp
        try:
            os.remove(dest_path)
        except FileNotFoundError:
            pass
        os.rename(tmp_path, dest_path)

    except Exception:
        # Clean up partial download
        for path in (tmp_path, dest_path):
            try:
                os.remove(path)
            except OSError:
                pass
        raise


def apply_update(current_exe: str, new_exe: str) -> None:
    """Spawn a detached .cmd script that swaps the exe after this process exits."""
    script_path = os.path.join(os.path.dirname(current_exe), "_talkie_update.cmd")
    pid = os.getpid()

    # All paths quoted for spaces. Rename-then-delete for safety:
    # old → _old, new → target, delete _old.
    old_backup = current_exe + ".old"
    script = f"""@echo off
:: Wait for PID {pid} to exit (up to ~20 seconds)
set attempts=0
:wait
tasklist /FI "PID eq {pid}" /NH /FO CSV 2>NUL | find /I ",{pid}," >NUL
if %ERRORLEVEL%==0 (
    set /a attempts+=1
    if %attempts% GEQ 20 goto fail
    ping -n 2 127.0.0.1 >NUL
    goto wait
)
:: Move old exe to backup (safe rollback point)
if exist "{old_backup}" del /F "{old_backup}"
move /Y "{current_exe}" "{old_backup}"
if %ERRORLEVEL% NEQ 0 goto fail
:: Move new exe into place
move /Y "{new_exe}" "{current_exe}"
if %ERRORLEVEL% NEQ 0 (
    :: Rollback: restore old exe
    move /Y "{old_backup}" "{current_exe}"
    goto fail
)
:: Clean up backup
del /F "{old_backup}"
:: Brief pause to let Windows fully release file locks before relaunch
ping -n 3 127.0.0.1 >NUL
:: Relaunch
start "" "{current_exe}"
:: Self-delete
del /F "%~f0"
exit /b 0
:fail
exit /b 1
"""
    with open(script_path, "w") as f:
        f.write(script)

    # Launch hidden and detached so it survives our exit
    subprocess.Popen(
        ["cmd.exe", "/c", script_path],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def cleanup_update_files(base_dir: str) -> None:
    """Remove stale update artifacts from a previous update."""
    stale = [
        os.path.join(base_dir, name)
        for name in ("Talkie_update.exe", "Talkie_update.exe.tmp",
                     "Talkie.exe.old", "_talkie_update.cmd")
    ]
    for path in stale:
        try:
            os.remove(path)
            logger.debug("Cleaned up stale update file: %s", path)
        except FileNotFoundError:
            pass  # already gone — expected on clean starts
        except OSError as exc:
            logger.debug("Could not clean up %s: %s", path, exc)
