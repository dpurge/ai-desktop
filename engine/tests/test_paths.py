import os
import stat
import sys
from pathlib import Path

import pytest

from backend.paths import ensure_private_dir, resolve_state_dir
from backend.session_store import SessionStore

HOME = Path("/home/u")


def test_macos():
    path = resolve_state_dir({}, "darwin", HOME)
    assert path == HOME / "Library" / "Application Support" / "ai-desktop"


def test_linux_uses_xdg_config_home():
    assert resolve_state_dir({"XDG_CONFIG_HOME": "/xdg"}, "linux", HOME) == Path("/xdg/ai-desktop")


@pytest.mark.parametrize("xdg", [None, "", "relative/dir"])
def test_linux_falls_back_to_dot_config(xdg):
    env = {} if xdg is None else {"XDG_CONFIG_HOME": xdg}
    assert resolve_state_dir(env, "linux", HOME) == HOME / ".config" / "ai-desktop"


def test_windows_uses_appdata():
    assert resolve_state_dir({"APPDATA": "/appdata"}, "win32", HOME) == Path("/appdata/ai-desktop")


def test_windows_without_appdata_falls_back_to_roaming():
    expected = HOME / "AppData" / "Roaming" / "ai-desktop"
    assert resolve_state_dir({}, "win32", HOME) == expected


@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_override_wins_on_every_platform(platform):
    assert resolve_state_dir({"AD_STATE_DIR": "/custom"}, platform, HOME) == Path("/custom")


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permission bits")
def test_ensure_private_dir_creates_nested_directories_owner_only(tmp_path):
    previous = os.umask(0o000)
    try:
        target = tmp_path / "state" / "sessions"
        ensure_private_dir(target)
    finally:
        os.umask(previous)

    assert stat.S_IMODE(target.stat().st_mode) == 0o700


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permission bits")
def test_ensure_private_dir_leaves_an_existing_directory_alone(tmp_path):
    tmp_path.chmod(0o755)
    ensure_private_dir(tmp_path)
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o755


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permission bits")
def test_session_store_directories_are_owner_only(tmp_path):
    SessionStore(tmp_path / "state")

    for directory in (tmp_path / "state", tmp_path / "state" / "sessions"):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
