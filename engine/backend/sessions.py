import re
from dataclasses import dataclass

SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
DEFAULT_TITLE = "New chat"
MAX_TITLE_LENGTH = 120
AUTO_TITLE_LENGTH = 40

_SESSION_ID = re.compile(SESSION_ID_PATTERN)


class InvalidSessionIdError(ValueError):
    """The id is not a plain token, so it must never reach the filesystem."""


class SessionNotFoundError(LookupError):
    pass


class SessionBusyError(RuntimeError):
    """The session has a running turn and cannot be changed or deleted."""


@dataclass(frozen=True)
class SessionSummary:
    id: str
    title: str
    model: str
    created_at: str
    updated_at: str
    message_count: int


def require_valid_session_id(session_id: str) -> str:
    # Session ids become file names, so this check guards against path traversal.
    if not _SESSION_ID.fullmatch(session_id):
        raise InvalidSessionIdError(f"Invalid session id: {session_id!r}")
    return session_id


def title_from_message(text: str) -> str:
    """Message folded onto one line and cut to 40 characters, with an ellipsis when cut."""
    single_line = " ".join(text.split())
    if len(single_line) <= AUTO_TITLE_LENGTH:
        return single_line
    return single_line[:AUTO_TITLE_LENGTH].rstrip() + "…"
