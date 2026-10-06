import sqlite3
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from backend.paths import ensure_private_dir
from backend.session_log import SessionLog
from backend.sessions import (
    DEFAULT_TITLE,
    SessionBusyError,
    SessionNotFoundError,
    SessionSummary,
    require_valid_session_id,
    title_from_message,
)

DATABASE_FILE_NAME = "sessions.db"
LOG_DIR_NAME = "sessions"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    renamed INTEGER NOT NULL DEFAULT 0,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0
)
"""
_SUMMARY_COLUMNS = "id, title, model, created_at, updated_at, message_count"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class SessionStore:
    """Session index in SQLite plus one JSONL transcript per session, both under state_dir.

    Every call is a short synchronous query on one shared connection guarded by a lock. That is
    acceptable because this is a single-user local engine: queries take microseconds, so briefly
    blocking the event loop costs nothing and avoids a thread pool.
    """

    def __init__(self, state_dir: Path, clock: Callable[[], str] = utc_now_iso) -> None:
        ensure_private_dir(state_dir)
        self._clock = clock
        self._log = SessionLog(state_dir / LOG_DIR_NAME)
        self._lock = threading.Lock()
        self._running_turns: set[str] = set()
        self._db = sqlite3.connect(state_dir / DATABASE_FILE_NAME, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock, self._db:
            self._db.execute(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def create(self, model: str, title: str = DEFAULT_TITLE) -> SessionSummary:
        session_id = uuid.uuid4().hex
        now = self._clock()
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO sessions (id, title, renamed, model, created_at, updated_at, "
                "message_count) VALUES (?, ?, 0, ?, ?, ?, 0)",
                (session_id, title, model, now, now),
            )
        return SessionSummary(session_id, title, model, now, now, 0)

    def list_all(self) -> list[SessionSummary]:
        with self._lock:
            rows = self._db.execute(
                f"SELECT {_SUMMARY_COLUMNS} FROM sessions ORDER BY updated_at DESC, rowid DESC"
            ).fetchall()
        return [SessionSummary(**dict(row)) for row in rows]

    def get(self, session_id: str) -> SessionSummary | None:
        require_valid_session_id(session_id)
        with self._lock:
            row = self._db.execute(
                f"SELECT {_SUMMARY_COLUMNS} FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return SessionSummary(**dict(row)) if row else None

    def messages(self, session_id: str) -> list[dict]:
        self._require_existing(session_id)
        return self._log.read(session_id)

    def rename(self, session_id: str, title: str) -> SessionSummary:
        self._require_existing(session_id)
        with self._lock, self._db:
            self._db.execute(
                "UPDATE sessions SET title = ?, renamed = 1, updated_at = ? WHERE id = ?",
                (title, self._clock(), session_id),
            )
        return self._require_existing(session_id)

    def delete(self, session_id: str) -> None:
        self._require_existing(session_id)
        with self._lock:
            if session_id in self._running_turns:
                raise SessionBusyError("Cannot delete a session while a turn is running")
            with self._db:
                self._db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self._log.delete(session_id)

    def append_message(
        self, session_id: str, role: str, content: str, extra: dict | None = None
    ) -> dict:
        """Log a message, then update the index. The log is the source of truth if they disagree.

        `extra` carries the OpenAI fields of tool messages (tool_calls, tool_call_id).
        """
        self._require_existing(session_id)
        message = {
            "id": uuid.uuid4().hex,
            "ts": self._clock(),
            "role": role,
            "content": content,
            **(extra or {}),
        }
        with self._lock:
            self._log.append(session_id, message)
            with self._db:
                self._db.execute(
                    "UPDATE sessions SET message_count = message_count + 1, updated_at = ? "
                    "WHERE id = ?",
                    (message["ts"], session_id),
                )
                if role == "user":
                    # Only the first message auto-titles, and only if the user has not renamed.
                    self._db.execute(
                        "UPDATE sessions SET title = ? "
                        "WHERE id = ? AND renamed = 0 AND message_count = 1",
                        (title_from_message(content), session_id),
                    )
        return message

    def try_begin_turn(self, session_id: str) -> bool:
        """Claim the session for one turn; False if it is unknown or already busy."""
        require_valid_session_id(session_id)
        with self._lock:
            exists = self._db.execute(
                "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not exists or session_id in self._running_turns:
                return False
            self._running_turns.add(session_id)
            return True

    def end_turn(self, session_id: str) -> None:
        with self._lock:
            self._running_turns.discard(session_id)

    def _require_existing(self, session_id: str) -> SessionSummary:
        session = self.get(session_id)
        if session is None:
            raise SessionNotFoundError(f"Unknown session: {session_id}")
        return session
