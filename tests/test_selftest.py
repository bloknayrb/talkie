"""Tests for the packaged-executable self-check."""

import ast
import pathlib
import sys

import pytest

from talkie_modules import selftest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _source_files() -> list[pathlib.Path]:
    return [REPO_ROOT / "main.py", *sorted((REPO_ROOT / "talkie_modules").glob("*.py"))]


def _module_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        # Relative imports resolve within the package and are always bundled.
        return [node.module] if node.module and node.level == 0 else []
    return []


def _collect_imports() -> tuple[set[str], set[str]]:
    """Return (top_level, deferred) module names across the codebase."""
    top_level: set[str] = set()
    deferred: set[str] = set()
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            top_level.update(_module_names(node))
        for parent in ast.walk(tree):
            if not isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(parent):
                deferred.update(_module_names(node))
    return top_level, deferred


class TestDeferredImportList:
    def test_list_covers_every_unbundled_deferred_import(self) -> None:
        """Guard against the list going stale as deferred imports are added.

        An import inside a function isn't exercised at startup, so a broken one
        surfaces late or — behind `except ImportError` — not at all. Anything
        not also imported at module scope has to be listed explicitly.
        """
        top_level, deferred = _collect_imports()
        unlisted = deferred - top_level - set(selftest.DEFERRED_IMPORTS)

        assert not unlisted, (
            "Deferred imports missing from selftest.DEFERRED_IMPORTS: "
            f"{sorted(unlisted)}. Add them, or a broken one will surface only "
            "when its code path runs — or never, if it sits behind "
            "`except ImportError`."
        )

    def test_no_duplicate_entries(self) -> None:
        entries = selftest.DEFERRED_IMPORTS
        assert len(entries) == len(set(entries))


class TestCheckImports:
    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="Windows-only dependencies (pywin32, winotify, keyboard) are "
        "not installable off Windows",
    )
    def test_every_deferred_import_resolves(self) -> None:
        """The regression guard for an undeclared dependency.

        A missing pywin32 made the Start Menu shortcut a no-op in shipped
        builds, swallowed by `except ImportError`. This fails instead.
        """
        failures = selftest.check_imports()
        assert not failures, f"unresolvable imports: {failures}"

    def test_failure_is_reported(self, monkeypatch) -> None:
        monkeypatch.setattr(
            selftest, "DEFERRED_IMPORTS", ("os", "talkie_modules_does_not_exist")
        )
        failures = selftest.check_imports()

        assert [name for name, _ in failures] == ["talkie_modules_does_not_exist"]
        assert "ModuleNotFoundError" in failures[0][1]


class TestRun:
    def test_returns_zero_and_writes_report_on_success(self, monkeypatch, tmp_path):
        monkeypatch.setattr(selftest, "DEFERRED_IMPORTS", ("os", "sys"))
        report = tmp_path / "selftest.log"

        assert selftest.run(str(report)) == 0
        assert "OK: all deferred imports resolved" in report.read_text()

    def test_returns_nonzero_and_names_the_failure(self, monkeypatch, tmp_path):
        monkeypatch.setattr(selftest, "DEFERRED_IMPORTS", ("no_such_module_xyz",))
        report = tmp_path / "selftest.log"

        assert selftest.run(str(report)) == 1
        text = report.read_text()
        assert "FAILED" in text
        assert "no_such_module_xyz" in text

    def test_unwritable_report_path_does_not_mask_the_result(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(selftest, "DEFERRED_IMPORTS", ("os",))
        # A bad report path must not turn a passing check into a crash.
        assert selftest.run(str(tmp_path / "missing_dir" / "r.log")) == 0
