from pathlib import Path

from backend.config import Config, load_config, save_config
from backend.secrets_store import SecretsStore


class SettingsService:
    """Single owner of the state dir's settings, so every turn reads what the user saved last."""

    def __init__(self, state_dir: Path, secrets: SecretsStore | None = None) -> None:
        self._state_dir = state_dir
        self.secrets = secrets if secrets is not None else SecretsStore(state_dir)

    @property
    def state_dir(self) -> Path:
        return self._state_dir

    def config(self) -> Config:
        # Re-read on demand: the file is tiny, and it keeps hand edits live as well as UI saves.
        return load_config(self._state_dir)

    def save(self, config: Config) -> None:
        save_config(self._state_dir, config)
