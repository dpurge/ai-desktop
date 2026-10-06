import asyncio
import os
import signal
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

MAX_OUTPUT_BYTES = 32 * 1024
TRUNCATION_MARKER = "\n[truncated]"
_READ_SIZE = 4096
# After a kill the pipes close at once; this only bounds a grandchild that escaped the group.
_DRAIN_GRACE_S = 2.0
_SECRET_NAME_SUFFIXES = ("_API_KEY", "_TOKEN", "_SECRET")
_ENGINE_NAME_PREFIX = "AD_"


@dataclass(frozen=True)
class ExecResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool


class Executor(Protocol):
    async def run(self, command: str, cwd: str, timeout_s: float) -> ExecResult:
        """Run a shell command; cancelling the awaiting task must stop the command."""
        ...


def child_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """The environment an approved command gets: the engine's own, minus its credentials.

    The user approves what a command does, not what it can read. Anything it prints goes to
    the remote model and into the session log, so the engine's token and provider keys must
    not be visible to it.
    """
    return {name: value for name, value in environ.items() if not _is_credential(name)}


def _is_credential(name: str) -> bool:
    upper = name.upper()
    return upper.startswith(_ENGINE_NAME_PREFIX) or upper.endswith(_SECRET_NAME_SUFFIXES)


class LocalExecutor:
    """Runs commands on this machine through the user's shell."""

    async def run(self, command: str, cwd: str, timeout_s: float) -> ExecResult:
        # shell=True semantics are intentional: the model writes shell command lines (pipes,
        # globs, &&), and every call is shown to the user for approval before it gets here.
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=Path(cwd).expanduser(),
            env=child_environment(os.environ),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # Own process group, so a kill also reaches the command's children.
            start_new_session=os.name != "nt",
        )
        output = _SharedBudgetReader(MAX_OUTPUT_BYTES)
        stdout_task = asyncio.create_task(output.read_all(process.stdout))
        stderr_task = asyncio.create_task(output.read_all(process.stderr))
        exit_task = asyncio.create_task(process.wait())
        tasks = {stdout_task, stderr_task, exit_task}
        try:
            _, still_running = await asyncio.wait(tasks, timeout=timeout_s)
            timed_out = bool(still_running)
            if timed_out:
                _kill(process)
                await asyncio.wait(tasks, timeout=_DRAIN_GRACE_S)
        except asyncio.CancelledError:
            _kill(process)
            raise
        finally:
            for task in tasks:
                task.cancel()
        return ExecResult(
            exit_code=process.returncode,
            stdout=_result_or_empty(stdout_task),
            stderr=_result_or_empty(stderr_task),
            timed_out=timed_out,
        )


class _SharedBudgetReader:
    """Reads pipes to the end, keeping at most `limit` bytes across all of them.

    Reading continues past the limit so a chatty command never blocks on a full pipe.
    """

    def __init__(self, limit: int) -> None:
        self._remaining = limit

    async def read_all(self, stream: asyncio.StreamReader) -> str:
        kept = bytearray()
        was_cut = False
        while chunk := await stream.read(_READ_SIZE):
            room = self._remaining
            kept += chunk[:room]
            self._remaining -= min(room, len(chunk))
            was_cut = was_cut or len(chunk) > room
        text = kept.decode("utf-8", errors="replace")
        return text + TRUNCATION_MARKER if was_cut else text


def _kill(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _result_or_empty(task: asyncio.Task) -> str:
    return task.result() if task.done() and not task.cancelled() else ""
