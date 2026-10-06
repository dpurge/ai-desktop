import asyncio
import uuid
from dataclasses import dataclass, field

from backend.interactions import InteractionRegistry


@dataclass
class Turn:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()


class TurnRegistry:
    """The running turn of each session, so a cancel request can find it."""

    def __init__(self, interactions: InteractionRegistry) -> None:
        self._interactions = interactions
        self._running: dict[str, Turn] = {}

    def start(self, session_id: str) -> Turn:
        turn = Turn()
        self._running[session_id] = turn
        return turn

    def finish(self, session_id: str) -> None:
        turn = self._running.pop(session_id, None)
        if turn is not None:
            # Nothing may stay answerable once its turn is over, for example after a disconnect.
            self._interactions.cancel_all(turn.id)

    def cancel(self, session_id: str) -> bool:
        turn = self._running.get(session_id)
        if turn is None:
            return False
        turn.cancel_event.set()
        self._interactions.cancel_all(turn.id)
        return True
