import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass

APPROVAL = "approval"
QUESTION = "question"
PROPOSAL = "proposal"

APPROVED = "approved"
DENIED = "denied"
ANSWERED = "answered"
ACCEPTED = "accepted"
REJECTED = "rejected"
TIMEOUT = "timeout"
CANCELLED = "cancelled"

MAX_ANSWER_CHARS = 4000
MAX_COMMENT_CHARS = 2000


class UnknownInteractionError(LookupError):
    """No pending interaction has this id: it never existed or is already resolved."""


class InvalidAnswerError(ValueError):
    """The answer does not fit the interaction's kind."""


@dataclass(frozen=True)
class Resolution:
    outcome: str
    answer: dict | None = None


@dataclass(frozen=True)
class Interaction:
    id: str
    kind: str
    payload: dict
    turn_id: str
    future: "asyncio.Future[Resolution]"


def _approval_outcome(answer: dict) -> str:
    decision = answer.get("decision")
    if decision == "approve":
        return APPROVED
    if decision == "deny":
        return DENIED
    raise InvalidAnswerError("'decision' must be 'approve' or 'deny'")


def _question_outcome(answer: dict) -> str:
    text = answer.get("answer")
    if not isinstance(text, str) or not text.strip():
        raise InvalidAnswerError("'answer' must be a non-empty string")
    if len(text.strip()) > MAX_ANSWER_CHARS:
        raise InvalidAnswerError(f"'answer' must be at most {MAX_ANSWER_CHARS} characters")
    return ANSWERED


def _proposal_outcome(answer: dict) -> str:
    comment = answer.get("comment")
    if comment is not None and not isinstance(comment, str):
        raise InvalidAnswerError("'comment' must be a string")
    if comment is not None and len(comment) > MAX_COMMENT_CHARS:
        raise InvalidAnswerError(f"'comment' must be at most {MAX_COMMENT_CHARS} characters")
    decision = answer.get("decision")
    if decision == "accept":
        return ACCEPTED
    if decision == "reject":
        return REJECTED
    raise InvalidAnswerError("'decision' must be 'accept' or 'reject'")


# One entry per kind: it checks an answer and names the outcome. A new kind is one more
# entry here, with no change to the registry.
_OUTCOME_OF_ANSWER: dict[str, Callable[[dict], str]] = {
    APPROVAL: _approval_outcome,
    QUESTION: _question_outcome,
    PROPOSAL: _proposal_outcome,
}


class InteractionRegistry:
    """Questions the engine has put to the user and is waiting on, keyed by id."""

    def __init__(self) -> None:
        self._pending: dict[str, Interaction] = {}

    def create(self, kind: str, payload: dict, turn_id: str) -> Interaction:
        if kind not in _OUTCOME_OF_ANSWER:
            raise ValueError(f"Unknown interaction kind: {kind!r}")
        interaction = Interaction(
            id=uuid.uuid4().hex,
            kind=kind,
            payload=payload,
            turn_id=turn_id,
            future=asyncio.get_running_loop().create_future(),
        )
        self._pending[interaction.id] = interaction
        return interaction

    async def await_answer(self, interaction: Interaction, timeout_s: float) -> Resolution:
        try:
            return await asyncio.wait_for(interaction.future, timeout_s)
        except TimeoutError:
            return Resolution(TIMEOUT)
        finally:
            # Also runs when the waiting task is cancelled, so nothing stays answerable.
            self._pending.pop(interaction.id, None)

    def pending(self) -> list[Interaction]:
        return list(self._pending.values())

    def resolve(self, interaction_id: str, answer: dict) -> None:
        interaction = self._pending.get(interaction_id)
        if interaction is None or interaction.future.done():
            raise UnknownInteractionError(f"No pending interaction {interaction_id}")
        outcome = _OUTCOME_OF_ANSWER[interaction.kind](answer)
        self._pending.pop(interaction_id)
        interaction.future.set_result(Resolution(outcome, answer))

    def cancel_all(self, turn_id: str) -> None:
        for interaction in list(self._pending.values()):
            if interaction.turn_id == turn_id and not interaction.future.done():
                self._pending.pop(interaction.id)
                interaction.future.set_result(Resolution(CANCELLED))
