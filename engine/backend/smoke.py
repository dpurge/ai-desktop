"""Manual check of the real provider path: python -m backend.smoke [ollama|openrouter]."""

import argparse
import asyncio
import dataclasses
import sys

from backend.config import PROVIDERS, Config, ConfigError, load_config
from backend.llm.aisuite_client import AisuiteLLM
from backend.llm.base import LLMError
from backend.paths import state_dir
from backend.secrets_store import SecretsStore
from backend.settings_service import SettingsService

PROMPT = "Reply with the single word: pong"
TIMEOUT_S = 120


class _FixedSettings(SettingsService):
    """Settings with the command-line provider applied, without saving it to disk."""

    def __init__(self, config: Config, secrets: SecretsStore) -> None:
        super().__init__(state_dir(), secrets)
        self._fixed = config

    def config(self) -> Config:
        return self._fixed


async def _stream_reply(llm: AisuiteLLM) -> None:
    async for delta in llm.stream([{"role": "user", "content": PROMPT}]):
        print(delta.text, end="", flush=True)
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backend.smoke", description=__doc__)
    parser.add_argument("provider", nargs="?", choices=PROVIDERS, help="default: from config")
    args = parser.parse_args(argv)

    directory = state_dir()
    secrets = SecretsStore(directory)
    try:
        config = load_config(directory)
        if args.provider:
            config = dataclasses.replace(config, provider=args.provider)
        if config.provider == "openrouter" and not secrets.has_api_key("openrouter"):
            print(
                "No OpenRouter API key: set OPENROUTER_API_KEY or store one first.", file=sys.stderr
            )
            return 2
        print(f"provider={config.provider} model={config.model}", file=sys.stderr)
        llm = AisuiteLLM(_FixedSettings(config, secrets))
        asyncio.run(asyncio.wait_for(_stream_reply(llm), TIMEOUT_S))
    except (ConfigError, LLMError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    except TimeoutError:
        print(f"FAILED: no complete reply within {TIMEOUT_S}s", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
