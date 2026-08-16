"""Tests for Start Menu shortcut management."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from talkie_modules.start_menu import create_start_menu_shortcut


class FakeShortcut:
    """Stand-in for the WScript.Shell shortcut COM object."""

    def __init__(self, target_path: str = "") -> None:
        self.TargetPath = target_path
        self.WorkingDirectory = ""
        self.IconLocation = ""
        self.saved = False

    def Save(self) -> None:
        self.saved = True


@pytest.fixture
def frozen_exe(monkeypatch, tmp_path):
    """Simulate a frozen build with APPDATA pointing at a temp dir."""
    exe = tmp_path / "dist" / "Talkie.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    return str(exe)


def _install_fake_win32com(monkeypatch, shortcut: FakeShortcut) -> MagicMock:
    """Make `import win32com.client` inside the function resolve to a fake."""
    shell = MagicMock()
    shell.CreateShortcut.return_value = shortcut
    dispatch = MagicMock(return_value=shell)

    client_mod = MagicMock()
    client_mod.Dispatch = dispatch
    win32com_mod = MagicMock()
    win32com_mod.client = client_mod

    monkeypatch.setitem(sys.modules, "win32com", win32com_mod)
    monkeypatch.setitem(sys.modules, "win32com.client", client_mod)
    return shell


class TestDevMode:
    def test_non_frozen_is_noop(self, monkeypatch) -> None:
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert create_start_menu_shortcut() is False


class TestAppdataGuard:
    """A missing APPDATA must bail out, not build a CWD-relative shortcut path.

    These install the fake win32com deliberately: without it the function
    would return False via ImportError regardless of the guard, and the test
    would pass even against the unguarded version.
    """

    def test_unset_appdata_returns_false(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.delenv("APPDATA", raising=False)
        sc = FakeShortcut()
        shell = _install_fake_win32com(monkeypatch, sc)

        assert create_start_menu_shortcut() is False
        shell.CreateShortcut.assert_not_called()
        assert not sc.saved

    def test_empty_appdata_returns_false(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setenv("APPDATA", "")
        sc = FakeShortcut()
        shell = _install_fake_win32com(monkeypatch, sc)

        assert create_start_menu_shortcut() is False
        shell.CreateShortcut.assert_not_called()


class TestShortcutCreation:
    def test_creates_shortcut_with_expected_fields(
        self, monkeypatch, frozen_exe, tmp_path
    ) -> None:
        sc = FakeShortcut()
        shell = _install_fake_win32com(monkeypatch, sc)

        assert create_start_menu_shortcut() is True
        assert sc.saved

        expected_path = os.path.join(
            str(tmp_path / "AppData"),
            "Microsoft", "Windows", "Start Menu", "Programs", "Talkie.lnk",
        )
        shell.CreateShortcut.assert_called_once_with(expected_path)
        assert sc.TargetPath == frozen_exe
        assert sc.WorkingDirectory == os.path.dirname(frozen_exe)

    def test_icon_location_is_exe_comma_zero(self, monkeypatch, frozen_exe) -> None:
        sc = FakeShortcut()
        _install_fake_win32com(monkeypatch, sc)

        create_start_menu_shortcut()

        # os.path.join would yield "...Talkie.exe\,0", which Windows cannot resolve.
        assert sc.IconLocation == frozen_exe + ",0"
        assert os.sep + ",0" not in sc.IconLocation

    def test_missing_win32com_returns_false(self, monkeypatch, frozen_exe) -> None:
        real_import = __import__

        def blocked(name, *args, **kwargs):
            if name.startswith("win32com"):
                raise ImportError("No module named 'win32com'")
            return real_import(name, *args, **kwargs)

        monkeypatch.delitem(sys.modules, "win32com", raising=False)
        monkeypatch.delitem(sys.modules, "win32com.client", raising=False)
        with patch("builtins.__import__", side_effect=blocked):
            assert create_start_menu_shortcut() is False

    def test_com_failure_is_swallowed(self, monkeypatch, frozen_exe) -> None:
        sc = FakeShortcut()
        shell = _install_fake_win32com(monkeypatch, sc)
        shell.CreateShortcut.side_effect = OSError("COM failure")

        assert create_start_menu_shortcut() is False


class TestStaleShortcutReconciliation:
    def _write_existing_lnk(self, tmp_path) -> str:
        programs = (
            tmp_path / "AppData" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        )
        programs.mkdir(parents=True)
        lnk = programs / "Talkie.lnk"
        lnk.write_text("")
        return str(lnk)

    def test_existing_shortcut_with_matching_target_is_left_alone(
        self, monkeypatch, frozen_exe, tmp_path
    ) -> None:
        self._write_existing_lnk(tmp_path)
        sc = FakeShortcut(target_path=frozen_exe)
        _install_fake_win32com(monkeypatch, sc)

        assert create_start_menu_shortcut() is True
        assert not sc.saved

    def test_stale_target_is_repointed_at_current_exe(
        self, monkeypatch, frozen_exe, tmp_path
    ) -> None:
        self._write_existing_lnk(tmp_path)
        sc = FakeShortcut(target_path=r"C:\old\location\Talkie.exe")
        _install_fake_win32com(monkeypatch, sc)

        assert create_start_menu_shortcut() is True
        assert sc.saved
        assert sc.TargetPath == frozen_exe
        assert sc.WorkingDirectory == os.path.dirname(frozen_exe)
