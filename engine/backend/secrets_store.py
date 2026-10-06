import json
import os
from collections.abc import Mapping
from pathlib import Path

from backend.paths import ensure_private_dir

SECRETS_FILE_NAME = "secrets.json"
_ENV_VARS = {"openrouter": "OPENROUTER_API_KEY"}


class SecretsStore:
    """API keys in state_dir/secrets.json (0600). Values are never put in errors or repr."""

    def __init__(self, state_dir: Path, env: Mapping[str, str] | None = None) -> None:
        self._path = state_dir / SECRETS_FILE_NAME
        self._env = os.environ if env is None else env

    def __repr__(self) -> str:
        return f"SecretsStore(path={str(self._path)!r})"

    def get_api_key(self, provider: str) -> str | None:
        # The environment wins so a developer can override the stored key without editing it.
        from_env = self._env.get(_ENV_VARS.get(provider, ""))
        if from_env:
            return from_env
        return self._read().get(provider) or None

    def has_api_key(self, provider: str) -> bool:
        return self.get_api_key(provider) is not None

    def set_api_key(self, provider: str, api_key: str) -> None:
        if not api_key.strip():
            raise ValueError("API key must not be empty")
        self._write({**self._read(), provider: api_key.strip()})

    def delete_api_key(self, provider: str) -> None:
        keys = self._read()
        if keys.pop(provider, None) is not None:
            self._write(keys)

    def _read(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            keys = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            # Not chained: a JSON error message can quote file content.
            raise ValueError(
                f"Cannot read {self._path} ({type(exc).__name__}). Delete it and set the key again."
            ) from None
        if not isinstance(keys, dict):
            raise ValueError(
                f"{self._path} must contain a JSON object. Delete it and set the key again."
            )
        return keys

    def _write(self, keys: dict[str, str]) -> None:
        ensure_private_dir(self._path.parent)
        temp = self._path.with_name(self._path.name + ".tmp")
        # O_EXCL + 0o600 means the content is never readable by others, even briefly.
        temp.unlink(missing_ok=True)
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(keys, handle)
        os.replace(temp, self._path)
