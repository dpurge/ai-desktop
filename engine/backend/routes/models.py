import dataclasses
from typing import Literal

from fastapi import APIRouter, HTTPException, Request

from backend.llm.models import ModelListError, list_models

router = APIRouter()


@router.get("/models")
async def read_models(
    request: Request, provider: Literal["ollama", "openrouter"] | None = None
) -> list[dict]:
    settings = request.app.state.settings
    config = settings.config()
    chosen = provider or config.provider
    try:
        models = await list_models(
            chosen,
            config.endpoints,
            settings.secrets.get_api_key(chosen),
            transport=request.app.state.http_transport,
        )
    except ModelListError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    return [dataclasses.asdict(model) for model in models]
