from types import SimpleNamespace

import httpx
import openai
import pytest
from aisuite.provider import LLMError as AisuiteLLMError

from backend.config import Config, ProviderEndpoints, save_config
from backend.llm.aisuite_client import AisuiteLLM
from backend.llm.base import Delta, LLMError, ToolCallFragment
from backend.secrets_store import SecretsStore
from backend.settings_service import SettingsService

KEY = "sk-or-very-secret-value"
MESSAGES = [{"role": "user", "content": "hi"}]


def chunk(content, with_choices=True):
    choices = [SimpleNamespace(delta=SimpleNamespace(content=content))] if with_choices else []
    return SimpleNamespace(choices=choices)


class FakeClient:
    """Stands in for aisuite.Client; records how it was used."""

    def __init__(self, chunks=None, error=None):
        self.calls = []
        self.provider_configs = None
        self._chunks = chunks or []
        self._error = error
        self.chat = SimpleNamespace(completions=SimpleNamespace(acreate=self._acreate))

    async def _acreate(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._iterate()

    async def _iterate(self):
        for item in self._chunks:
            yield item


def make_llm(tmp_path, client, provider="ollama", key=None):
    config = Config(
        provider=provider,
        model="gemma4:12b",
        endpoints=ProviderEndpoints("http://ollama.test:11434", "https://or.test/api/v1"),
    )
    save_config(tmp_path, config)
    secrets = SecretsStore(tmp_path, env={})
    if key:
        secrets.set_api_key("openrouter", key)

    def factory(provider_configs):
        client.provider_configs = provider_configs
        return client

    return AisuiteLLM(SettingsService(tmp_path, secrets), client_factory=factory)


async def collect(llm):
    return [delta async for delta in llm.stream(MESSAGES)]


async def test_streams_text_and_skips_empty_deltas(tmp_path):
    client = FakeClient([chunk("Hel"), chunk(None), chunk(""), chunk(None, False), chunk("lo")])

    deltas = await collect(make_llm(tmp_path, client))

    assert deltas == [Delta("Hel"), Delta("lo")]
    assert client.calls == [{"model": "ollama:gemma4:12b", "messages": MESSAGES, "stream": True}]


async def test_ollama_config_uses_base_url_only(tmp_path):
    client = FakeClient()
    await collect(make_llm(tmp_path, client))
    assert set(client.provider_configs) == {"ollama"}
    assert client.provider_configs["ollama"]["base_url"] == "http://ollama.test:11434"


async def test_openrouter_config_carries_key_and_url(tmp_path):
    client = FakeClient()
    await collect(make_llm(tmp_path, client, provider="openrouter", key=KEY))
    assert client.provider_configs == {
        "openrouter": {"api_key": KEY, "base_url": "https://or.test/api/v1"}
    }
    assert client.calls[0]["model"] == "openrouter:gemma4:12b"


async def test_missing_openrouter_key_is_readable_and_skips_client(tmp_path):
    client = FakeClient()
    with pytest.raises(LLMError, match="OpenRouter API key is not set"):
        await collect(make_llm(tmp_path, client, provider="openrouter"))
    assert client.calls == []


def wrapped(openai_error):
    """Mimics aisuite, which re-raises provider errors as its own LLMError."""
    try:
        try:
            raise openai_error
        except Exception as exc:
            raise AisuiteLLMError(f"An error occurred: {exc}") from exc
    except AisuiteLLMError as outer:
        return outer


def status_error(error_class, status):
    request = httpx.Request("POST", "http://x")
    response = httpx.Response(status, request=request, json={"error": KEY})
    return error_class(f"boom {KEY}", response=response, body=None)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            openai.APIConnectionError(request=httpx.Request("POST", "http://x")),
            "Cannot reach Ollama at http://ollama.test:11434",
        ),
        (status_error(openai.AuthenticationError, 401), "Ollama rejected the API key"),
        (status_error(openai.NotFoundError, 404), "Ollama has no model 'gemma4:12b'"),
        (status_error(openai.InternalServerError, 500), "Ollama returned an error (HTTP 500)"),
    ],
)
async def test_provider_errors_map_to_readable_llm_error(tmp_path, error, expected):
    client = FakeClient(error=wrapped(error))

    with pytest.raises(LLMError) as caught:
        await collect(make_llm(tmp_path, client))

    assert expected in str(caught.value)
    assert KEY not in str(caught.value)


async def test_unknown_error_is_generic_without_details(tmp_path):
    client = FakeClient(error=RuntimeError(f"leak {KEY}"))

    with pytest.raises(LLMError) as caught:
        await collect(make_llm(tmp_path, client))

    assert KEY not in str(caught.value)
    assert "RuntimeError" in str(caught.value)


def tool_chunk(*calls, content=None):
    raw = [
        SimpleNamespace(index=i, id=cid, function=SimpleNamespace(name=name, arguments=args))
        for i, cid, name, args in calls
    ]
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=raw))]
    )


async def test_tools_are_passed_through_and_fragments_mapped(tmp_path):
    schemas = [{"type": "function", "function": {"name": "shell"}}]
    client = FakeClient(
        [
            tool_chunk((0, "c1", "shell", '{"comm')),
            tool_chunk((0, None, None, 'and": "ls"}')),
        ]
    )

    llm = make_llm(tmp_path, client)
    deltas = [d async for d in llm.stream(MESSAGES, schemas)]

    assert client.calls[0]["tools"] == schemas
    assert "max_turns" not in client.calls[0]
    assert deltas == [
        Delta(tool_calls=(ToolCallFragment(0, "c1", "shell", '{"comm'),)),
        Delta(tool_calls=(ToolCallFragment(0, None, None, 'and": "ls"}'),)),
    ]


async def test_no_tools_key_when_none_are_offered(tmp_path):
    client = FakeClient()
    await collect(make_llm(tmp_path, client))
    assert "tools" not in client.calls[0]
