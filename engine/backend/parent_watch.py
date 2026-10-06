import ctypes
import os
import sys
import threading
import time
from collections.abc import Callable

PARENT_PID_ENV_VAR = "AD_PARENT_PID"
POLL_SECONDS = 2.0

# Windows: OpenProcess succeeds for a live process and for one that exited but is still referenced,
# so the exit code must be checked too.
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259


def _is_process_alive_windows(pid: int) -> bool:
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _is_process_alive_windows(pid)
    try:
        os.kill(pid, 0)  # signal 0 only checks existence and permission
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but belongs to someone else
    return True


def parse_parent_pid(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        pid = int(raw)
    except ValueError:
        return None
    return pid if pid > 0 else None


def watch_parent(
    pid: int,
    on_parent_gone: Callable[[], None],
    poll_seconds: float = POLL_SECONDS,
) -> threading.Thread:
    """Call on_parent_gone once the parent process no longer exists (daemon thread)."""

    def loop() -> None:
        while is_process_alive(pid):
            time.sleep(poll_seconds)
        on_parent_gone()

    thread = threading.Thread(target=loop, name="parent-watch", daemon=True)
    thread.start()
    return thread


def start_from_env() -> None:
    """Exit this process when the launcher named in AD_PARENT_PID dies (no orphaned engine)."""
    pid = parse_parent_pid(os.environ.get(PARENT_PID_ENV_VAR))
    if pid is not None:
        # os._exit: uvicorn runs in the main thread, so sys.exit here would only end this thread.
        watch_parent(pid, lambda: os._exit(0))
