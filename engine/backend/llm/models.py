import ssl
from dataclasses import dataclass

import httpx

from backend.config import ProviderEndpoints

_PROVIDER_LABELS = {"ollama": "Ollama", "openrouter": "OpenRouter"}
_TIMEOUT_S = 10


class ModelListError(Exception):
    """The provider's model list could not be fetched; the message is safe to show the user."""


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str


async def list_models(
    provider: str,
    endpoints: ProviderEndpoints,
    api_key: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[ModelInfo]:
    """Models offered by the provider, sorted by id. `transport` lets tests avoid the network."""
    base_url = endpoints.base_url_for(provider).rstrip("/")
    label = _PROVIDER_LABELS[provider]
    if provider == "ollama":
        url, headers, parse = f"{base_url}/api/tags", {}, _parse_ollama
    else:
        # The OpenRouter listing is public; a key is sent only when one exists.
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        url, parse = f"{base_url}/models", _parse_openrouter

    payload = await _get_json(url, headers, transport, label, base_url)
    try:
        return sorted(parse(payload), key=lambda model: model.id)
    except (KeyError, TypeError, AttributeError):
        raise ModelListError(f"{label} returned a model list in an unexpected format.") from None


async def _get_json(url, headers, transport, label: str, base_url: str):
    try:
        async with httpx.AsyncClient(transport=transport, timeout=_TIMEOUT_S) as http:
            response = await http.get(url, headers=headers)
    except httpx.HTTPError as exc:
        # Not chained or detailed: the request headers may carry the key.
        if _has_untrusted_certificate(exc):
            # Typical behind a TLS-inspecting proxy; "cannot reach" would send users the wrong way.
            raise ModelListError(
                f"Cannot verify the TLS certificate of {label} at {base_url}"
            ) from None
        raise ModelListError(f"Cannot reach {label} at {base_url}") from None
    if response.status_code in (401, 403):
        raise ModelListError(f"{label} rejected the API key. Check it in settings.")
    if response.status_code != 200:
        raise ModelListError(f"{label} returned an error (HTTP {response.status_code}).")
    try:
        return response.json()
    except ValueError:
        raise ModelListError(f"{label} returned a model list in an unexpected format.") from None


def _has_untrusted_certificate(exc: BaseException) -> bool:
    # httpx wraps httpcore, which wraps the ssl error, so look down the whole chain.
    while exc is not None:
        if isinstance(exc, ssl.SSLCertVerificationError):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def _parse_ollama(payload: dict) -> list[ModelInfo]:
    models = []
    for entry in payload["models"]:
        # Embedding-only models cannot chat. Older servers send no capabilities, so keep those.
        capabilities = entry.get("capabilities")
        if capabilities is not None and "completion" not in capabilities:
            continue
        models.append(ModelInfo(id=entry["name"], name=entry["name"]))
    return models


def _parse_openrouter(payload: dict) -> list[ModelInfo]:
    return [
        ModelInfo(id=entry["id"], name=entry.get("name") or entry["id"])
        for entry in payload["data"]
    ]
