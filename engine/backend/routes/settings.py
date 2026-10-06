import dataclasses
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, StrictBool, StringConstraints, field_validator

from backend.config import Config, SandboxConfig
from backend.settings_service import SettingsService
from backend.tools.openshell import OpenShellStatus

router = APIRouter()

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
# Only OpenRouter has a key today; Ollama needs none.
KeyedProvider = Literal["openrouter"]


class _Strict(BaseModel):
    # Unknown fields are rejected so a typo never looks like a successful save.
    model_config = ConfigDict(extra="forbid")


class EndpointUpdate(_Strict):
    base_url: NonEmptyText

    @field_validator("base_url")
    @classmethod
    def must_be_http_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return value


class SandboxUpdate(_Strict):
    enabled: StrictBool


class SettingsUpdate(_Strict):
    provider: Literal["ollama", "openrouter"] | None = None
    model: NonEmptyText | None = None
    ollama: EndpointUpdate | None = None
    openrouter: EndpointUpdate | None = None
    theme: Literal["system", "light", "dark"] | None = None
    sandbox: SandboxUpdate | None = None


class ApiKeyUpdate(_Strict):
    provider: KeyedProvider
    api_key: NonEmptyText


def get_settings_service(request: Request) -> SettingsService:
    return request.app.state.settings


@router.get("/settings")
def read_settings(request: Request) -> dict:
    return _describe(get_settings_service(request), request.app.state.detect_sandbox())


@router.put("/settings")
def update_settings(body: SettingsUpdate, request: Request) -> dict:
    settings = get_settings_service(request)
    status = request.app.state.detect_sandbox()
    if body.sandbox and body.sandbox.enabled and not status.available:
        # Refused here too, so the toggle cannot be forced on through the API.
        raise HTTPException(status_code=422, detail=status.reason)
    settings.save(_apply(settings.config(), body))
    return _describe(settings, status)


@router.put("/settings/api-key", status_code=204)
def set_api_key(body: ApiKeyUpdate, request: Request) -> Response:
    get_settings_service(request).secrets.set_api_key(body.provider, body.api_key)
    return Response(status_code=204)


@router.delete("/settings/api-key", status_code=204)
def delete_api_key(provider: KeyedProvider, request: Request) -> Response:
    get_settings_service(request).secrets.delete_api_key(provider)
    return Response(status_code=204)


def _apply(config: Config, update: SettingsUpdate) -> Config:
    endpoints = config.endpoints
    if update.ollama:
        endpoints = dataclasses.replace(endpoints, ollama_base_url=update.ollama.base_url)
    if update.openrouter:
        endpoints = dataclasses.replace(endpoints, openrouter_base_url=update.openrouter.base_url)
    # replace() keeps the settings this screen does not edit (tools, approval) intact.
    return dataclasses.replace(
        config,
        provider=update.provider or config.provider,
        model=update.model or config.model,
        endpoints=endpoints,
        theme=update.theme or config.theme,
        sandbox=_apply_sandbox(config.sandbox, update.sandbox),
    )


def _apply_sandbox(current: SandboxConfig, update: SandboxUpdate | None) -> SandboxConfig:
    return current if update is None else SandboxConfig(enabled=update.enabled)


def _describe(settings: SettingsService, sandbox: OpenShellStatus) -> dict:
    config = settings.config()
    return {
        "provider": config.provider,
        "model": config.model,
        "ollama": {"base_url": config.endpoints.ollama_base_url},
        "openrouter": {"base_url": config.endpoints.openrouter_base_url},
        # Presence only: the key itself is write-only and never leaves the engine.
        "has_api_key": {"openrouter": settings.secrets.has_api_key("openrouter")},
        "theme": config.theme,
        "sandbox": {
            "enabled": config.sandbox.enabled,
            "available": sandbox.available,
            "reason": sandbox.reason,
        },
    }
