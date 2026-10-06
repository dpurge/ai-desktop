from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request, Response
from pydantic import BaseModel, StringConstraints

from backend.session_store import SessionStore
from backend.sessions import (
    MAX_TITLE_LENGTH,
    SESSION_ID_PATTERN,
    SessionBusyError,
    SessionNotFoundError,
)

router = APIRouter()

SessionId = Annotated[str, Path(pattern=SESSION_ID_PATTERN)]
Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TITLE_LENGTH)
]


class CreateSession(BaseModel):
    title: Title | None = None


class RenameSession(BaseModel):
    title: Title


def get_store(request: Request) -> SessionStore:
    return request.app.state.session_store


@router.get("/sessions")
def list_sessions(request: Request) -> list[dict]:
    return [asdict(session) for session in get_store(request).list_all()]


@router.post("/sessions", status_code=201)
def create_session(request: Request, body: CreateSession | None = None) -> dict:
    options = {"title": body.title} if body and body.title else {}
    session = get_store(request).create(model=request.app.state.model_name(), **options)
    return asdict(session)


@router.get("/sessions/{session_id}")
def get_session(session_id: SessionId, request: Request) -> dict:
    store = get_store(request)
    session = _existing(store, session_id)
    return {"session": asdict(session), "messages": store.messages(session_id)}


@router.patch("/sessions/{session_id}")
def rename_session(session_id: SessionId, body: RenameSession, request: Request) -> dict:
    store = get_store(request)
    _existing(store, session_id)
    return asdict(store.rename(session_id, body.title))


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: SessionId, request: Request) -> Response:
    try:
        get_store(request).delete(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Unknown session") from None
    except SessionBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return Response(status_code=204)


def _existing(store: SessionStore, session_id: str):
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    return session
