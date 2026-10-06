import os
import subprocess
import sys
import threading

from backend.parent_watch import is_process_alive, parse_parent_pid, watch_parent


def _finished_child_pid() -> int:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()  # reaped, so the pid is really gone
    return child.pid


def test_current_process_is_alive():
    assert is_process_alive(os.getpid())


def test_finished_process_is_not_alive():
    assert not is_process_alive(_finished_child_pid())


def test_non_positive_pids_are_not_alive():
    assert not is_process_alive(0)
    assert not is_process_alive(-1)


def test_parse_parent_pid():
    assert parse_parent_pid("123") == 123
    assert parse_parent_pid(None) is None
    assert parse_parent_pid("") is None
    assert parse_parent_pid("abc") is None
    assert parse_parent_pid("0") is None


def test_watch_parent_calls_back_when_parent_is_gone():
    gone = threading.Event()
    watch_parent(_finished_child_pid(), gone.set, poll_seconds=0.01)
    assert gone.wait(timeout=5)


def test_watch_parent_stays_quiet_while_parent_lives():
    gone = threading.Event()
    watch_parent(os.getpid(), gone.set, poll_seconds=0.01)
    assert not gone.wait(timeout=0.2)
