import logging
from collections.abc import AsyncIterator, Callable
from contextlib import aclosing
from dataclasses import dataclass, field

from backend.agent.cancellation import CANCELLED, run_unless_cancelled
from backend.agent.history import CANCELLED_TOOL_RESULT
from backend.agent.prompt import SYSTEM_PROMPT, with_system_prompt
from backend.agent.tool_calls import InvalidArgumentsError, ToolCall, ToolCallAccumulator
from backend.agent.turns import Turn
from backend.interactions import (
    APPROVAL,
    APPROVED,
    DENIED,
    TIMEOUT,
    InteractionRegistry,
    Resolution,
)
from backend.interactions import CANCELLED as INTERACTION_CANCELLED
from backend.llm.base import LLM, LLMError
from backend.tools.registry import ToolContext, ToolOutcome, ToolRegistry, ToolSpec

logger = logging.getLogger(__name__)

MAX_STEPS = 8

_RESULT_FOR_UNANSWERED = {
    DENIED: "The user denied this command.",
    TIMEOUT: "No response from the user; treated as denied.",
    INTERACTION_CANCELLED: CANCELLED_TOOL_RESULT,
}


@dataclass(frozen=True)
class Event:
    name: str
    data: dict


@dataclass(frozen=True)
class TurnServices:
    llm: LLM
    tools: ToolRegistry
    tool_context: ToolContext
    interactions: InteractionRegistry
    approval_timeout_s: float
    max_steps: int = MAX_STEPS
    system_prompt: str = SYSTEM_PROMPT


class _Transcript:
    """The history sent to the model, kept in step with the stored session log."""

    def __init__(
        self, history: list[dict], record: Callable[[dict], None], system_prompt: str
    ) -> None:
        self._history = history
        self._system_prompt = system_prompt
        self._record = record
        self._answered_call_ids: set[str] = set()

    def add(self, message: dict) -> None:
        self._history.append(message)
        self._record(message)
        if message["role"] == "tool":
            self._answered_call_ids.add(message["tool_call_id"])

    def has_result_for(self, call_id: str) -> bool:
        return call_id in self._answered_call_ids

    def model_request(self) -> list[dict]:
        return with_system_prompt(self._history, self._system_prompt)


@dataclass
class _ModelRound:
    """What the model produced in one request."""

    text_parts: list[str] = field(default_factory=list)
    accumulator: ToolCallAccumulator = field(default_factory=ToolCallAccumulator)
    calls: list[ToolCall] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(self.text_parts)

    def finish(self) -> None:
        # Calls count only once the stream ended: a cut-off call has unusable arguments.
        self.calls = self.accumulator.calls()


async def run_turn(
    services: TurnServices,
    turn: Turn,
    history: list[dict],
    record: Callable[[dict], None],
) -> AsyncIterator[Event]:
    """Run the model and its tool calls until it answers, yielding what the GUI should show.

    `history` is extended in place and every added message is passed to `record`.
    """
    yield Event("turn_started", {"turn_id": turn.id})
    try:
        async for event in _run_steps(
            services, turn, _Transcript(history, record, services.system_prompt)
        ):
            yield event
    except Exception as exc:
        # The stream is already open, so the failure has to travel as an event, not an HTTP status.
        logger.exception("Turn failed")
        yield Event("error", {"code": "llm_error", "message": _user_message(exc)})
        yield Event("turn_done", {"reason": "error"})


async def _run_steps(
    services: TurnServices, turn: Turn, transcript: _Transcript
) -> AsyncIterator[Event]:
    for _ in range(services.max_steps):
        model_round = _ModelRound()
        try:
            async for event in _stream_model(services, turn, transcript, model_round):
                yield event
        finally:
            # Also on failure or disconnect, so the log keeps what the user already saw.
            _record_assistant_message(transcript, model_round)
        if turn.is_cancelled:
            # The assistant message above already announced these calls.
            _answer_unanswered_calls(transcript, model_round.calls)
            yield Event("turn_done", {"reason": "cancelled"})
            return
        if not model_round.calls:
            yield Event("turn_done", {"reason": "completed"})
            return
        async for event in _run_tool_calls(services, turn, transcript, model_round.calls):
            yield event
        if turn.is_cancelled:
            yield Event("turn_done", {"reason": "cancelled"})
            return
    yield Event("turn_done", {"reason": "max_steps"})


async def _stream_model(
    services: TurnServices, turn: Turn, transcript: _Transcript, model_round: _ModelRound
) -> AsyncIterator[Event]:
    schemas = services.tools.openai_schemas() or None
    async with aclosing(services.llm.stream(transcript.model_request(), schemas)) as stream:
        while True:
            delta = await run_unless_cancelled(_next_delta(stream), turn.cancel_event)
            if delta is CANCELLED:
                return
            if delta is None:
                break
            if delta.text:
                model_round.text_parts.append(delta.text)
                yield Event("text_delta", {"text": delta.text})
            for fragment in delta.tool_calls:
                model_round.accumulator.add(fragment)
    model_round.finish()


async def _next_delta(stream):
    return await anext(stream, None)


def _record_assistant_message(transcript: _Transcript, model_round: _ModelRound) -> None:
    if not model_round.text and not model_round.calls:
        return
    message: dict = {"role": "assistant", "content": model_round.text}
    if model_round.calls:
        message["tool_calls"] = [call.as_openai() for call in model_round.calls]
    transcript.add(message)


async def _run_tool_calls(
    services: TurnServices, turn: Turn, transcript: _Transcript, calls: list[ToolCall]
) -> AsyncIterator[Event]:
    try:
        for call in calls:
            async for event in _handle_call(services, turn, transcript, call):
                yield event
            if turn.is_cancelled:
                return
    finally:
        _answer_unanswered_calls(transcript, calls)


def _answer_unanswered_calls(transcript: _Transcript, calls: list[ToolCall]) -> None:
    # Providers reject a history where a tool call has no result, so a cut-short turn
    # still answers every call it announced.
    for call in calls:
        if not transcript.has_result_for(call.id):
            transcript.add(_tool_message(call.id, CANCELLED_TOOL_RESULT))


@dataclass
class _Verdict:
    outcome: str = APPROVED
    resolution: Resolution | None = None


async def _handle_call(
    services: TurnServices, turn: Turn, transcript: _Transcript, call: ToolCall
) -> AsyncIterator[Event]:
    spec = services.tools.get(call.name)
    arguments, argument_error = _parse_arguments(call)
    yield Event("tool_call", {"call_id": call.id, "name": call.name, "arguments": arguments})
    failure = argument_error or _missing_tool_or_arguments(spec, arguments, call.name)
    if failure:
        result = ToolOutcome(False, failure)
    elif spec.interaction:
        verdict = _Verdict()
        payload = spec.interaction.payload(arguments)
        async for event in _request_interaction(
            services, turn, spec, call, spec.interaction.kind, payload, verdict
        ):
            yield event
        result = spec.interaction.result(verdict.resolution)
    else:
        verdict = _Verdict()
        if spec.requires_approval:
            details = spec.approval_details(arguments)
            async for event in _request_interaction(
                services, turn, spec, call, APPROVAL, details, verdict
            ):
                yield event
        if verdict.outcome == APPROVED:
            result = await _run_tool(services, turn, spec, arguments)
        else:
            result = ToolOutcome(False, _RESULT_FOR_UNANSWERED[verdict.outcome])
    transcript.add(_tool_message(call.id, result.output))
    yield Event(
        "tool_result",
        {"call_id": call.id, "name": call.name, "ok": result.ok, "output": result.output},
    )


def _parse_arguments(call: ToolCall) -> tuple[dict, str | None]:
    try:
        return call.arguments(), None
    except InvalidArgumentsError as exc:
        return {}, f"Invalid arguments for {call.name}: {exc}. Send a JSON object."


def _missing_tool_or_arguments(spec: ToolSpec | None, arguments: dict, name: str) -> str | None:
    if spec is None:
        return f"Unknown tool: {name}"
    missing = [key for key in spec.required_arguments if key not in arguments]
    if missing:
        return f"Missing required argument(s) for {name}: {', '.join(missing)}"
    return spec.validate_arguments(arguments)


async def _request_interaction(
    services: TurnServices,
    turn: Turn,
    spec: ToolSpec,
    call: ToolCall,
    kind: str,
    payload: dict,
    verdict: _Verdict,
) -> AsyncIterator[Event]:
    interaction = services.interactions.create(kind, {"tool": spec.name, **payload}, turn.id)
    yield Event(
        "interaction_required",
        {
            "interaction_id": interaction.id,
            "kind": kind,
            "tool": spec.name,
            "call_id": call.id,
            "payload": payload,
            "timeout_s": services.approval_timeout_s,
        },
    )
    resolution = await services.interactions.await_answer(interaction, services.approval_timeout_s)
    verdict.outcome = resolution.outcome
    verdict.resolution = resolution
    yield Event(
        "interaction_resolved",
        {"interaction_id": interaction.id, "outcome": resolution.outcome},
    )


async def _run_tool(
    services: TurnServices, turn: Turn, spec: ToolSpec, arguments: dict
) -> ToolOutcome:
    async def run() -> ToolOutcome:
        try:
            return await spec.run(arguments, services.tool_context)
        except Exception as exc:
            logger.exception("Tool %s failed", spec.name)
            return ToolOutcome(
                False, f"The {spec.name} tool failed unexpectedly ({type(exc).__name__})."
            )

    outcome = await run_unless_cancelled(run(), turn.cancel_event)
    return ToolOutcome(False, CANCELLED_TOOL_RESULT) if outcome is CANCELLED else outcome


def _tool_message(call_id: str, content: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def _user_message(exc: Exception) -> str:
    # Only LLMError text is vetted for users; anything else could echo request details or secrets.
    if isinstance(exc, LLMError):
        return str(exc)
    return f"Unexpected engine error ({type(exc).__name__}). See the engine log for details."
