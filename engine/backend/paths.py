import os
import sys
from collections.abc import Mapping
from pathlib import Path

APP_DIR_NAME = "ai-desktop"
STATE_DIR_ENV_VAR = "AD_STATE_DIR"


def resolve_state_dir(env: Mapping[str, str], platform: str, home: Path) -> Path:
    """Pure variant of state_dir() so every OS branch can be tested on any machine."""
    override = env.get(STATE_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser()
    if platform == "darwin":
        return home / "Library" / "Application Support" / APP_DIR_NAME
    if platform.startswith("win"):
        appdata = env.get("APPDATA")
        return (Path(appdata) if appdata else home / "AppData" / "Roaming") / APP_DIR_NAME
    return _xdg_config_home(env, home) / APP_DIR_NAME


def _xdg_config_home(env: Mapping[str, str], home: Path) -> Path:
    configured = env.get("XDG_CONFIG_HOME")
    # The XDG spec says relative values must be ignored.
    if configured and Path(configured).is_absolute():
        return Path(configured)
    return home / ".config"


def ensure_private_dir(path: Path) -> None:
    """Create the directory readable by this user only; an existing one keeps its mode."""
    existed = path.exists()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    # mkdir's mode is reduced by the umask, so a new directory is tightened explicitly.
    if not existed and os.name != "nt":
        path.chmod(0o700)


def state_dir() -> Path:
    return resolve_state_dir(os.environ, sys.platform, Path.home())
