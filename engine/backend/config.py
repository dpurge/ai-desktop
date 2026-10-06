import copy
import os
import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import tomli_w

from backend.paths import ensure_private_dir

CONFIG_FILE_NAME = "config.toml"
PROVIDERS = ("ollama", "openrouter")
# "system" leaves the choice to the OS light/dark preference.
THEMES = ("system", "light", "dark")
MAX_SHELL_TIMEOUT_S = 3600
MAX_APPROVAL_TIMEOUT_S = 86_400


class ConfigError(Exception):
    """The configuration is unreadable or invalid; the message says how to fix it."""


@dataclass(frozen=True)
class ProviderEndpoints:
    ollama_base_url: str
    openrouter_base_url: str

    def base_url_for(self, provider: str) -> str:
        return {"ollama": self.ollama_base_url, "openrouter": self.openrouter_base_url}[provider]


@dataclass(frozen=True)
class ShellConfig:
    enabled: bool = True
    cwd: str = "~"
    timeout_s: int = 60


@dataclass(frozen=True)
class SkillsConfig:
    # An extra folder of skill folders, e.g. a project's; empty means none.
    workspace_dir: str = ""


@dataclass(frozen=True)
class SandboxConfig:
    # Off by default: commands run directly on this machine, as the approval card says.
    enabled: bool = False


@dataclass(frozen=True)
class Config:
    provider: str
    model: str
    endpoints: ProviderEndpoints
    theme: str = "system"
    shell: ShellConfig = ShellConfig()
    approval_timeout_s: int = 600
    skills: SkillsConfig = SkillsConfig()
    sandbox: SandboxConfig = SandboxConfig()


def load_config(state_dir: Path) -> Config:
    """Built-in defaults overlaid with state_dir/config.toml, validated."""
    config_path = state_dir / CONFIG_FILE_NAME
    merged = _merge(_read_defaults(), _read_user_file(config_path))
    return _validate(merged, config_path)


def save_config(state_dir: Path, config: Config) -> None:
    document = {
        "provider": config.provider,
        "model": config.model,
        "ollama": {"base_url": config.endpoints.ollama_base_url},
        "openrouter": {"base_url": config.endpoints.openrouter_base_url},
        "ui": {"theme": config.theme},
        "tools": {
            "shell": {
                "enabled": config.shell.enabled,
                "cwd": config.shell.cwd,
                "timeout_s": config.shell.timeout_s,
            }
        },
        "approval": {"timeout_s": config.approval_timeout_s},
        "skills": {"workspace_dir": config.skills.workspace_dir},
        "sandbox": {"enabled": config.sandbox.enabled},
    }
    ensure_private_dir(state_dir)
    target = state_dir / CONFIG_FILE_NAME
    # Replace via a temp file so a crash never leaves a half-written config behind.
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(tomli_w.dumps(document), encoding="utf-8")
    os.replace(temp, target)


def _read_defaults() -> dict:
    text = resources.files("backend").joinpath("defaults", CONFIG_FILE_NAME).read_text("utf-8")
    return tomllib.loads(text)


def _read_user_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise ConfigError(
            f"Cannot read {path}: {exc}. Fix the file or delete it to reset."
        ) from exc


def _merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _validate(raw: dict, path: Path) -> Config:
    provider = raw.get("provider")
    if provider not in PROVIDERS:
        raise ConfigError(
            f"Unknown provider {provider!r} in {path}. Set provider to one of: "
            f"{', '.join(PROVIDERS)}."
        )
    return Config(
        provider=provider,
        model=_require_text(raw.get("model"), "model", path),
        endpoints=ProviderEndpoints(
            ollama_base_url=_require_url(raw, "ollama", path),
            openrouter_base_url=_require_url(raw, "openrouter", path),
        ),
        theme=_require_theme(raw, path),
        shell=_require_shell(raw, path),
        approval_timeout_s=_require_seconds(
            _table(raw, "approval"), "approval.timeout_s", MAX_APPROVAL_TIMEOUT_S, path
        ),
        skills=_require_skills(raw, path),
        sandbox=_require_sandbox(raw, path),
    )


def _require_text(value: object, key: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"'{key}' in {path} must be a non-empty string.")
    return value.strip()


def _require_url(raw: dict, section: str, path: Path) -> str:
    table = raw.get(section)
    value = table.get("base_url") if isinstance(table, dict) else None
    url = _require_text(value, f"{section}.base_url", path)
    if not url.startswith(("http://", "https://")):
        raise ConfigError(f"'{section}.base_url' in {path} must start with http:// or https://.")
    return url


def _require_theme(raw: dict, path: Path) -> str:
    table = raw.get("ui")
    theme = table.get("theme") if isinstance(table, dict) else None
    if theme not in THEMES:
        raise ConfigError(f"'ui.theme' in {path} must be one of: {', '.join(THEMES)}.")
    return theme


def _table(raw: dict, name: str) -> dict:
    table = raw.get(name)
    return table if isinstance(table, dict) else {}


def _require_shell(raw: dict, path: Path) -> ShellConfig:
    shell = _table(_table(raw, "tools"), "shell")
    enabled = shell.get("enabled")
    if not isinstance(enabled, bool):
        raise ConfigError(f"'tools.shell.enabled' in {path} must be true or false.")
    return ShellConfig(
        enabled=enabled,
        cwd=_require_text(shell.get("cwd"), "tools.shell.cwd", path),
        timeout_s=_require_seconds(shell, "tools.shell.timeout_s", MAX_SHELL_TIMEOUT_S, path),
    )


def _require_skills(raw: dict, path: Path) -> SkillsConfig:
    workspace_dir = _table(raw, "skills").get("workspace_dir")
    if not isinstance(workspace_dir, str):
        raise ConfigError(f"'skills.workspace_dir' in {path} must be text; use \"\" for none.")
    return SkillsConfig(workspace_dir=workspace_dir.strip())


def _require_sandbox(raw: dict, path: Path) -> SandboxConfig:
    enabled = _table(raw, "sandbox").get("enabled")
    if not isinstance(enabled, bool):
        raise ConfigError(f"'sandbox.enabled' in {path} must be true or false.")
    return SandboxConfig(enabled=enabled)


def _require_seconds(table: dict, key: str, maximum: int, path: Path) -> int:
    value = table.get("timeout_s")
    # bool is an int subclass, and "timeout_s = true" must not pass as 1 second.
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ConfigError(
            f"'{key}' in {path} must be a whole number of seconds from 1 to {maximum}."
        )
    return value
