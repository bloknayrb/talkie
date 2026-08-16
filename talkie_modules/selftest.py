"""Runtime self-check for the packaged executable.

Imports that happen inside a function are not exercised at startup, so when one
is unsatisfiable the app launches fine and fails later — on the code path that
needs it, possibly never during testing. Worse, an import wrapped in
`try/except ImportError` degrades silently and never fails at all: that is how
a missing pywin32 shipped in a green build with the Start Menu shortcut inert.

(PyInstaller itself does find function-level imports — it scans bytecode, not
just module scope. The gap this closes is a dependency that was never declared
in requirements.txt, so nothing was installed for PyInstaller to bundle and
`--hidden-import` degraded to a build warning.)

Importing all of them up front turns that class of failure into a loud one. Run
against the frozen exe via `Talkie.exe --selftest`, and against the dev
environment by `tests/test_selftest.py`.
"""

import importlib
import sys
from typing import List, Tuple

# Every import that happens inside a function and is not also imported at module
# scope anywhere — i.e. everything not already proven reachable at startup.
# tests/test_selftest.py fails if this list falls behind the codebase.
DEFERRED_IMPORTS: Tuple[str, ...] = (
    # Third-party reached only via deferred imports.
    "anthropic",
    "keyboard",
    "openai",
    "pystray",
    "pyperclip",
    "sounddevice",
    "soundfile",
    "winotify",
    # COM support for the Start Menu shortcut. Imported inside a try/except
    # ImportError, so its absence is invisible without this check.
    "pythoncom",
    "win32com.client",
    # Stdlib reached only via deferred imports.
    "shutil",
    "socket",
    "tempfile",
    "webbrowser",
    # First-party modules not reachable from main.py's top-level import graph.
    "talkie_modules.autostart",
    "talkie_modules.history",
    "talkie_modules.icon_generator",
    "talkie_modules.local_whisper",
    "talkie_modules.ollama_utils",
    "talkie_modules.start_menu",
    "talkie_modules.updater",
)


def check_imports() -> List[Tuple[str, str]]:
    """Import every deferred module. Returns (module, error) for each failure."""
    failures: List[Tuple[str, str]] = []
    for name in DEFERRED_IMPORTS:
        try:
            importlib.import_module(name)
        except Exception as e:
            failures.append((name, f"{type(e).__name__}: {e}"))
    return failures


def run(report_path: str = "") -> int:
    """Run the self-check, optionally writing a report. Returns an exit code.

    The packaged exe is built with --noconsole, so stdout goes nowhere when it
    is launched from a shell. Writing the report to a file is what makes the
    result visible to CI.
    """
    failures = check_imports()

    lines = [f"Talkie self-test ({len(DEFERRED_IMPORTS)} deferred imports)"]
    lines.append(f"frozen={getattr(sys, 'frozen', False)} executable={sys.executable}")
    if failures:
        lines.append(f"FAILED: {len(failures)} import(s) could not be resolved")
        lines.extend(f"  {name}: {error}" for name, error in failures)
    else:
        lines.append("OK: all deferred imports resolved")
    report = "\n".join(lines)

    print(report)
    if report_path:
        try:
            with open(report_path, "w", encoding="utf-8") as fh:
                fh.write(report + "\n")
        except OSError as e:
            print(f"Could not write report to {report_path}: {e}")

    return 1 if failures else 0
