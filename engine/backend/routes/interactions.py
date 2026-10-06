from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.interactions import InvalidAnswerError, UnknownInteractionError

router = APIRouter()


@router.post("/interactions/{interaction_id}")
def answer_interaction(interaction_id: str, body: dict[str, Any], request: Request) -> dict:
    try:
        request.app.state.interactions.resolve(interaction_id, body)
    except UnknownInteractionError:
        raise HTTPException(status_code=404, detail="Unknown or already answered") from None
    except InvalidAnswerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"resolved": True}
