"""Tests for Start Menu shortcut management."""

import os
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

from talkie_modules.start_menu import (
    create_start_menu_shortcut,
    create_start_menu_shortcut_async,
)


class FakeShortcut:
    """Stand-in for the WScript.Shell shortcut COM object."""

    def __init__(
        self,
        target_path: str = "",
        working_directory: str = "",
        icon_location: str = "",
    ) -> None:
        self.TargetPath = target_path
        self.WorkingDirectory = working_directory
        self.IconLocation = icon_location
        self.saved = False
        self.save_error: Exception | None = None

    def Save(self) -> None:
        if self.save_error is not None:
            raise self.save_error
        self.saved = True


def matching_shortcut(exe: str) -> FakeShortcut:
    """A shortcut already fully consistent with `exe` — the no-op case."""
    return FakeShortcut(
        target_path=exe,
        working_directory=os.path.dirname(exe),
        icon_location=exe + ",0",
    )


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
    """Make the deferred `pythoncom` / `win32com.client` imports resolve to fakes."""
    shell = MagicMock()
    shell.CreateShortcut.return_value = shortcut
    dispatch = MagicMock(return_value=shell)

    client_mod = MagicMock()
    client_mod.Dispatch = dispatch
    win32com_mod = MagicMock()
    win32com_mod.client = client_mod

    monkeypatch.setitem(sys.modules, "win32com", win32com_mod)
    monkeypatch.setitem(sys.modules, "win32com.client", client_mod)
    monkeypatch.setitem(sys.modules, "pythoncom", MagicMock())
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
            if name.startswith("win32com") or name == "pythoncom":
                raise ImportError(f"No module named {name!r}")
            return real_import(name, *args, **kwargs)

        monkeypatch.delitem(sys.modules, "win32com", raising=False)
        monkeypatch.delitem(sys.modules, "win32com.client", raising=False)
        monkeypatch.delitem(sys.modules, "pythoncom", raising=False)
        with patch("builtins.__import__", side_effect=blocked):
            assert create_start_menu_shortcut() is False

    def test_com_failure_is_swallowed(self, monkeypatch, frozen_exe) -> None:
        sc = FakeShortcut()
        shell = _install_fake_win32com(monkeypatch, sc)
        shell.CreateShortcut.side_effect = OSError("COM failure")

        assert create_start_menu_shortcut() is False

    def test_save_failure_is_swallowed(self, monkeypatch, frozen_exe) -> None:
        # The realistic Windows failure: no write access to Start Menu\Programs.
        sc = FakeShortcut()
        sc.save_error = PermissionError("Access is denied")
        _install_fake_win32com(monkeypatch, sc)

        assert create_start_menu_shortcut() is False

    def test_dispatches_wscript_shell(self, monkeypatch, frozen_exe) -> None:
        sc = FakeShortcut()
        _install_fake_win32com(monkeypatch, sc)

        create_start_menu_shortcut()

        dispatch = sys.modules["win32com.client"].Dispatch
        dispatch.assert_called_once_with("WScript.Shell")

    def test_creates_programs_dir_when_missing(
        self, monkeypatch, frozen_exe, tmp_path
    ) -> None:
        sc = FakeShortcut()
        _install_fake_win32com(monkeypatch, sc)
        programs = (
            tmp_path / "AppData" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        )
        assert not programs.exists()

        assert create_start_menu_shortcut() is True
        assert programs.is_dir()


class TestStaleShortcutReconciliation:
    def _write_existing_lnk(self, tmp_path) -> str:
        programs = (
            tmp_path / "AppData" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        )
        programs.mkdir(parents=True)
        lnk = programs / "Talkie.lnk"
        lnk.write_text("")
        return str(lnk)

    def test_existing_matching_shortcut_is_left_alone(
        self, monkeypatch, frozen_exe, tmp_path
    ) -> None:
        lnk = self._write_existing_lnk(tmp_path)
        sc = matching_shortcut(frozen_exe)
        shell = _install_fake_win32com(monkeypatch, sc)

        assert create_start_menu_shortcut() is True
        assert not sc.saved
        # The shortcut must actually have been opened and inspected. Without
        # this, the pre-fix code — which early-returned on os.path.isfile()
        # before touching COM at all — would satisfy the assertions above.
        shell.CreateShortcut.assert_called_once_with(lnk)

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

    def test_stale_icon_is_repaired_even_when_target_matches(
        self, monkeypatch, frozen_exe, tmp_path
    ) -> None:
        self._write_existing_lnk(tmp_path)
        # Written by a build carrying the os.path.join icon bug.
        sc = matching_shortcut(frozen_exe)
        sc.IconLocation = os.path.join(frozen_exe, ",0")
        _install_fake_win32com(monkeypatch, sc)

        assert create_start_menu_shortcut() is True
        assert sc.saved
        assert sc.IconLocation == frozen_exe + ",0"

    def test_stale_working_directory_is_repaired_when_target_matches(
        self, monkeypatch, frozen_exe, tmp_path
    ) -> None:
        self._write_existing_lnk(tmp_path)
        sc = matching_shortcut(frozen_exe)
        sc.WorkingDirectory = r"C:\old\location"
        _install_fake_win32com(monkeypatch, sc)

        assert create_start_menu_shortcut() is True
        assert sc.saved
        assert sc.WorkingDirectory == os.path.dirname(frozen_exe)

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="os.path.normcase is a no-op on POSIX; case-folding is Windows-only",
    )
    def test_target_comparison_is_case_insensitive(
        self, monkeypatch, frozen_exe, tmp_path
    ) -> None:
        self._write_existing_lnk(tmp_path)
        # Shell can hand TargetPath back in a different case than we wrote.
        sc = matching_shortcut(frozen_exe)
        sc.TargetPath = frozen_exe.upper()
        sc.IconLocation = (frozen_exe + ",0").upper()
        _install_fake_win32com(monkeypatch, sc)

        assert create_start_menu_shortcut() is True
        # Case-only drift is not drift; re-saving on every launch is the bug.
        assert not sc.saved

    def test_unreadable_shortcut_is_discarded_and_recreated(
        self, monkeypatch, frozen_exe, tmp_path
    ) -> None:
        lnk = self._write_existing_lnk(tmp_path)
        sc = FakeShortcut()
        shell = _install_fake_win32com(monkeypatch, sc)
        # First open fails (corrupt / not really a .lnk), second succeeds.
        shell.CreateShortcut.side_effect = [OSError("not a shortcut"), sc]

        assert create_start_menu_shortcut() is True
        assert not os.path.exists(lnk) or sc.saved
        assert sc.saved
        assert sc.TargetPath == frozen_exe
        assert shell.CreateShortcut.call_count == 2


class TestComApartment:
    """COM apartments are per-thread, so the worker thread must initialize its own."""

    def test_com_is_initialized_and_released(self, monkeypatch, frozen_exe) -> None:
        sc = FakeShortcut()
        _install_fake_win32com(monkeypatch, sc)

        assert create_start_menu_shortcut() is True

        pythoncom = sys.modules["pythoncom"]
        pythoncom.CoInitialize.assert_called_once_with()
        pythoncom.CoUninitialize.assert_called_once_with()

    def test_com_is_released_even_when_save_fails(self, monkeypatch, frozen_exe) -> None:
        sc = FakeShortcut()
        sc.save_error = PermissionError("Access is denied")
        _install_fake_win32com(monkeypatch, sc)

        assert create_start_menu_shortcut() is False

        # Leaking an apartment on the failure path would be invisible until the
        # next COM user on this thread.
        sys.modules["pythoncom"].CoUninitialize.assert_called_once_with()

    def test_uninitialize_skipped_when_initialize_rejected(
        self, monkeypatch, frozen_exe
    ) -> None:
        sc = FakeShortcut()
        _install_fake_win32com(monkeypatch, sc)
        pythoncom = sys.modules["pythoncom"]
        # RPC_E_CHANGED_MODE: an apartment already exists under another model.
        pythoncom.CoInitialize.side_effect = OSError("RPC_E_CHANGED_MODE")

        assert create_start_menu_shortcut() is True
        # Unbalanced CoUninitialize would tear down someone else's apartment.
        pythoncom.CoUninitialize.assert_not_called()


class TestAsyncLaunch:
    def test_runs_on_a_daemon_thread_and_completes(
        self, monkeypatch, frozen_exe
    ) -> None:
        sc = FakeShortcut()
        _install_fake_win32com(monkeypatch, sc)

        thread = create_start_menu_shortcut_async()
        assert thread.daemon
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert sc.saved

    def test_caller_is_not_blocked_by_a_hung_com_call(
        self, monkeypatch, frozen_exe
    ) -> None:
        release = threading.Event()
        sc = FakeShortcut()
        shell = _install_fake_win32com(monkeypatch, sc)

        def hang(_path):
            release.wait(timeout=10)
            return sc

        shell.CreateShortcut.side_effect = hang

        try:
            thread = create_start_menu_shortcut_async()
            # The point of the worker thread: startup proceeds while COM hangs.
            assert thread.is_alive()
            assert not sc.saved
        finally:
            release.set()
            thread.join(timeout=5)

        assert sc.saved
