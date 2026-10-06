from collections.abc import AsyncIterator, Callable
from contextlib import aclosing
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, StringConstraints

from backend.agent.history import repair_tool_results
from backend.agent.loop import TurnServices, run_turn
from backend.agent.prompt import build_system_prompt
from backend.agent.turns import Turn
from backend.routes.sessions import SessionId
from backend.session_store import SessionStore
from backend.skills.loader import skill_scanner
from backend.sse import format_event
from backend.tools.executor_factory import select_executor
from backend.tools.registry import ToolContext, registry_for

router = APIRouter()

# Fields a provider understands; the log also carries ids and timestamps it does not accept.
_MESSAGE_FIELDS = ("role", "content", "tool_calls", "tool_call_id")
# Bounds what one request can add to the log and send to the provider.
MAX_MESSAGE_CHARS = 100_000


class UserMessage(BaseModel):
    text: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)
    ]


@router.post("/sessions/{session_id}/messages")
async def post_message(session_id: SessionId, body: UserMessage, request: Request):
    state = request.app.state
    store: SessionStore = state.session_store
    if store.get(session_id) is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    # Read before the turn is claimed, so a broken config cannot leave the session busy.
    config = state.settings.config()
    if not store.try_begin_turn(session_id):
        raise HTTPException(status_code=409, detail="A turn is already running for this session")

    try:
        store.append_message(session_id, "user", body.text)
        history = _llm_history(store, session_id)
        executor = state.executor or select_executor(config.sandbox, state.detect_sandbox())
        scan_skills = skill_scanner(state.settings.state_dir, config.skills.workspace_dir)
        services = TurnServices(
            llm=state.llm,
            tools=registry_for(config, scan_skills),
            tool_context=ToolContext(executor=executor),
            interactions=state.interactions,
            approval_timeout_s=config.approval_timeout_s,
            system_prompt=build_system_prompt(scan_skills().skills),
        )
        turn = state.turns.start(session_id)
    except Exception:
        store.end_turn(session_id)
        raise
    stream = _stream_turn(request, services, turn, session_id, history)
    return StreamingResponse(stream, media_type="text/event-stream")


@router.post("/sessions/{session_id}/cancel")
async def cancel_turn(session_id: SessionId, request: Request) -> dict:
    return {"cancelled": request.app.state.turns.cancel(session_id)}


def _llm_history(store: SessionStore, session_id: str) -> list[dict]:
    return [
        {field: message[field] for field in _MESSAGE_FIELDS if field in message}
        for message in repair_tool_results(store.messages(session_id))
    ]


def _recorder(store: SessionStore, session_id: str) -> Callable[[dict], None]:
    def record(message: dict) -> None:
        extra = {k: v for k, v in message.items() if k not in ("role", "content")}
        store.append_message(session_id, message["role"], message["content"], extra)

    return record


async def _stream_turn(
    request: Request,
    services: TurnServices,
    turn: Turn,
    session_id: str,
    history: list[dict],
) -> AsyncIterator[bytes]:
    store: SessionStore = request.app.state.session_store
    events = run_turn(services, turn, history, _recorder(store, session_id))
    try:
        async with aclosing(events):
            async for event in events:
                yield format_event(event.name, event.data)
    finally:
        # Also runs on client disconnect: the cancellation has already stopped the running
        # tool, and this ends whatever the turn still had open.
        try:
            request.app.state.turns.finish(session_id)
        finally:
            store.end_turn(session_id)
