import os
from collections.abc import AsyncIterator, Callable

import aisuite
import openai

from backend.config import Config, ConfigError
from backend.llm.base import Delta, LLMError, ToolCallFragment
from backend.settings_service import SettingsService

_PROVIDER_LABELS = {"ollama": "Ollama", "openrouter": "OpenRouter"}
# aisuite's own OpenRouter provider has no streaming support, so OpenRouter runs through the
# OpenAI provider with OpenRouter's base_url (OpenRouter is OpenAI-compatible). Ollama already
# has a dedicated provider and keeps it.
_AISUITE_PROVIDER_KEYS = {"ollama": "ollama", "openrouter": "openai"}
# Local models can take a while to load before the first token; aisuite's default is 30 s.
_OLLAMA_TIMEOUT_S = 120


class AisuiteLLM:
    """The only adapter around aisuite: turns settings + secrets into streamed Deltas."""

    def __init__(
        self,
        settings: SettingsService,
        client_factory: Callable[..., aisuite.Client] = aisuite.Client,
    ) -> None:
        self._settings = settings
        self._client_factory = client_factory

    async def stream(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> AsyncIterator[Delta]:
        config = self._current_config()
        # aisuite splits "provider:model" on the first colon only, so "ollama:gemma4:12b"
        # reaches Ollama as model "gemma4:12b". OpenRouter goes through the OpenAI provider
        # (see _AISUITE_PROVIDER_KEYS) because its own provider cannot stream.
        model = f"{_AISUITE_PROVIDER_KEYS[config.provider]}:{config.model}"
        try:
            # Config is read and the client built per call, so saved settings (model, endpoint,
            # key) apply to the next turn without a restart.
            client = self._client_factory(provider_configs=self._provider_configs(config))
            # No max_turns: aisuite's own tool loop cannot stream, and the engine runs tools itself.
            options = {"tools": tools} if tools else {}
            chunks = await client.chat.completions.acreate(
                model=model, messages=messages, stream=True, **options
            )
            async for chunk in chunks:
                delta = _chunk_delta(chunk)
                if delta.text or delta.tool_calls:
                    yield delta
        except LLMError:
            raise
        except Exception as exc:
            raise _to_llm_error(exc, config) from None

    def _current_config(self) -> Config:
        try:
            return self._settings.config()
        except ConfigError as exc:
            raise LLMError(str(exc)) from None

    def _provider_configs(self, config: Config) -> dict[str, dict]:
        provider = config.provider
        base_url = config.endpoints.base_url_for(provider)
        if provider == "ollama":
            return {"ollama": {"base_url": base_url, "timeout": _OLLAMA_TIMEOUT_S}}
        api_key = self._settings.secrets.get_api_key(provider)
        if not api_key:
            raise LLMError("OpenRouter API key is not set. Add it in settings.")
        # Only the active provider is configured: aisuite builds every configured provider
        # eagerly, and OpenRouter refuses to build without a key. The "openai" key is deliberate.
        return {"openai": _with_openrouter_attribution(api_key, base_url)}


def _with_openrouter_attribution(api_key: str, base_url: str) -> dict:
    """OpenRouter's optional attribution headers, matching what its own provider set."""
    provider_config = {"api_key": api_key, "base_url": base_url}
    headers = {}
    if os.getenv("OR_SITE_URL"):
        headers["HTTP-Referer"] = os.environ["OR_SITE_URL"]
    if os.getenv("OR_APP_NAME"):
        headers["X-OpenRouter-Title"] = os.environ["OR_APP_NAME"]
    if headers:
        provider_config["default_headers"] = headers
    return provider_config


def _to_llm_error(exc: Exception, config: Config) -> LLMError:
    provider = config.provider
    label = _PROVIDER_LABELS[provider]
    # aisuite wraps provider failures in its own LLMError, so the original sits in the chain.
    original = _find_openai_error(exc)
    if isinstance(original, openai.APIConnectionError):
        return LLMError(f"Cannot reach {label} at {config.endpoints.base_url_for(provider)}")
    if isinstance(original, openai.AuthenticationError):
        return LLMError(f"{label} rejected the API key. Check it in settings.")
    if isinstance(original, openai.NotFoundError):
        return LLMError(f"{label} has no model '{config.model}'. Pick another model.")
    if isinstance(original, openai.APIStatusError):
        return LLMError(f"{label} returned an error (HTTP {original.status_code}).")
    return LLMError(f"{label} request failed ({type(exc).__name__}).")


def _chunk_delta(chunk) -> Delta:
    if not chunk.choices:
        return Delta()
    delta = chunk.choices[0].delta
    fragments = tuple(
        _tool_call_fragment(position, raw)
        for position, raw in enumerate(getattr(delta, "tool_calls", None) or [])
    )
    return Delta(text=delta.content or "", tool_calls=fragments)


def _tool_call_fragment(position: int, raw) -> ToolCallFragment:
    function = getattr(raw, "function", None)
    index = getattr(raw, "index", None)
    return ToolCallFragment(
        # Some servers omit the index when a call arrives whole; position then identifies it.
        index=index if index is not None else position,
        id=getattr(raw, "id", None),
        name=getattr(function, "name", None),
        arguments_fragment=getattr(function, "arguments", None) or "",
    )


def _find_openai_error(exc: BaseException | None) -> openai.OpenAIError | None:
    seen = set()
    while exc is not None and id(exc) not in seen:
        if isinstance(exc, openai.OpenAIError):
            return exc
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return None
