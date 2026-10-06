import ssl

import httpx
import pytest

from backend.config import ProviderEndpoints
from backend.llm.models import ModelInfo, ModelListError, list_models
from tests.conftest import AUTH

ENDPOINTS = ProviderEndpoints("http://ollama.test:11434/", "https://or.test/api/v1")
KEY = "sk-test-not-real"


def transport_returning(payload=None, status=200, record=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if record is not None:
            record.append(request)
        return httpx.Response(status, json=payload, text=None if payload else "server body")

    return httpx.MockTransport(handler)


def transport_failing():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"refused with {request.headers.get('authorization')}")

    return httpx.MockTransport(handler)


OLLAMA_TAGS = {
    "models": [
        {"name": "zeta:1b", "capabilities": ["completion", "tools"]},
        {"name": "nomic-embed-text:latest", "capabilities": ["embedding"]},
        {"name": "alpha:7b"},
    ]
}
OPENROUTER_LIST = {
    "data": [
        {"id": "vendor/b", "name": "Vendor B"},
        {"id": "vendor/a"},
    ]
}


async def test_ollama_models_are_sorted_and_embedding_only_models_dropped():
    seen = []

    models = await list_models(
        "ollama", ENDPOINTS, transport=transport_returning(OLLAMA_TAGS, record=seen)
    )

    assert models == [ModelInfo("alpha:7b", "alpha:7b"), ModelInfo("zeta:1b", "zeta:1b")]
    assert str(seen[0].url) == "http://ollama.test:11434/api/tags"


async def test_openrouter_models_use_id_and_fall_back_to_it_for_name():
    models = await list_models(
        "openrouter", ENDPOINTS, transport=transport_returning(OPENROUTER_LIST)
    )

    assert models == [ModelInfo("vendor/a", "vendor/a"), ModelInfo("vendor/b", "Vendor B")]


async def test_openrouter_sends_the_key_only_when_one_exists():
    seen = []
    transport = transport_returning(OPENROUTER_LIST, record=seen)

    await list_models("openrouter", ENDPOINTS, None, transport)
    await list_models("openrouter", ENDPOINTS, KEY, transport)

    assert "authorization" not in seen[0].headers
    assert seen[1].headers["authorization"] == f"Bearer {KEY}"
    assert str(seen[1].url) == "https://or.test/api/v1/models"


@pytest.mark.parametrize(
    ("provider", "transport", "message"),
    [
        ("ollama", transport_failing(), "Cannot reach Ollama at http://ollama.test:11434"),
        ("openrouter", transport_returning({}, 401), "OpenRouter rejected the API key"),
        ("openrouter", transport_returning({}, 503), "OpenRouter returned an error (HTTP 503)"),
        (
            "ollama",
            transport_returning({"nope": 1}),
            "Ollama returned a model list in an unexpected",
        ),
        ("ollama", transport_returning(None), "Ollama returned a model list in an unexpected"),
    ],
)
async def test_failures_map_to_readable_errors_without_server_bodies(provider, transport, message):
    with pytest.raises(ModelListError) as caught:
        await list_models(provider, ENDPOINTS, KEY, transport)

    assert message in str(caught.value)
    assert "server body" not in str(caught.value)
    assert KEY not in str(caught.value)


async def test_route_defaults_to_the_current_provider_and_returns_id_and_name(make_client):
    async with make_client(http_transport=transport_returning(OLLAMA_TAGS)) as client:
        response = await client.get("/models", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == [
        {"id": "alpha:7b", "name": "alpha:7b"},
        {"id": "zeta:1b", "name": "zeta:1b"},
    ]


async def test_route_uses_the_stored_key_for_openrouter(make_client, settings):
    seen = []
    settings.secrets.set_api_key("openrouter", KEY)
    transport = transport_returning(OPENROUTER_LIST, record=seen)

    async with make_client(http_transport=transport) as client:
        response = await client.get("/models?provider=openrouter", headers=AUTH)

    assert response.status_code == 200
    assert seen[0].headers["authorization"] == f"Bearer {KEY}"
    assert KEY not in response.text


async def test_route_maps_provider_failure_to_502(make_client):
    async with make_client(http_transport=transport_failing()) as client:
        response = await client.get("/models?provider=ollama", headers=AUTH)

    assert response.status_code == 502
    assert response.json()["detail"] == "Cannot reach Ollama at http://localhost:11434"


async def test_route_rejects_unknown_provider(client):
    assert (await client.get("/models?provider=acme", headers=AUTH)).status_code == 422


async def test_untrusted_certificate_is_reported_as_such_not_as_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        # Same shape as the real chain: httpx error -> transport error -> ssl error.
        transport_error = ConnectionError("tls")
        transport_error.__cause__ = ssl.SSLCertVerificationError("self-signed")
        raise httpx.ConnectError("tls") from transport_error

    with pytest.raises(ModelListError, match="Cannot verify the TLS certificate of OpenRouter"):
        await list_models("openrouter", ENDPOINTS, transport=httpx.MockTransport(handler))
