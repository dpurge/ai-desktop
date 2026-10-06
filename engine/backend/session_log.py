import json
import logging
from pathlib import Path

from backend.paths import ensure_private_dir
from backend.sessions import require_valid_session_id

logger = logging.getLogger(__name__)


class SessionLogCorruptError(RuntimeError):
    pass


class SessionLog:
    """Append-only JSONL transcript, one file per session and one message per line."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        ensure_private_dir(directory)

    def append(self, session_id: str, message: dict) -> None:
        path = self._path(session_id)
        _drop_partial_final_line(path)
        line = json.dumps(message, ensure_ascii=False)
        with path.open("a", encoding="utf-8", newline="\n") as log_file:
            log_file.write(line + "\n")

    def read(self, session_id: str) -> list[dict]:
        path = self._path(session_id)
        if not path.exists():
            return []
        lines = path.read_bytes().split(b"\n")
        last_line_number = max((n for n, line in enumerate(lines, 1) if line.strip()), default=0)
        messages = []
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                messages.append(json.loads(line))
            except ValueError as exc:
                if line_number == last_line_number:
                    # A crash mid-write leaves a partial last line; earlier messages are intact.
                    # Only the position is logged: the line is user content.
                    logger.warning("Ignoring unreadable last line %d of %s", line_number, path)
                    continue
                raise SessionLogCorruptError(
                    f"{path.name} line {line_number} is not valid JSON: {exc}. "
                    "Remove or repair that line."
                ) from exc
        return messages

    def delete(self, session_id: str) -> None:
        self._path(session_id).unlink(missing_ok=True)

    def _path(self, session_id: str) -> Path:
        return self._directory / f"{require_valid_session_id(session_id)}.jsonl"


def _drop_partial_final_line(path: Path) -> None:
    """Make the next append start on its own line after a crash cut the last write short.

    A complete message that only lacks its newline is kept. An unreadable fragment is cut off:
    left in place it would turn into a corrupt line in the middle, which fails every later read.
    """
    if not path.exists() or path.stat().st_size == 0:
        return
    with path.open("r+b") as log_file:
        log_file.seek(-1, 2)
        if log_file.read(1) == b"\n":
            return
        log_file.seek(0)
        content = log_file.read()
        tail_start = content.rfind(b"\n") + 1
        try:
            json.loads(content[tail_start:])
        except ValueError:
            log_file.truncate(tail_start)
        else:
            log_file.seek(0, 2)
            log_file.write(b"\n")
