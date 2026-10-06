import json

import pytest

from backend.session_store import SessionStore
from backend.sessions import (
    InvalidSessionIdError,
    SessionBusyError,
    SessionNotFoundError,
    title_from_message,
)


class TickingClock:
    """Distinct, increasing timestamps so ordering tests do not depend on wall time."""

    def __init__(self) -> None:
        self._tick = 0

    def __call__(self) -> str:
        self._tick += 1
        return f"2026-01-01T00:00:{self._tick:02d}.000+00:00"


@pytest.fixture
def store(tmp_path):
    return SessionStore(tmp_path, clock=TickingClock())


def test_create_records_model_and_default_title(store):
    session = store.create(model="m1")
    assert (session.title, session.model, session.message_count) == ("New chat", "m1", 0)
    assert len(session.id) == 32
    assert store.get(session.id) == session


def test_get_unknown_returns_none(store):
    assert store.get("missing") is None


def test_list_is_ordered_by_updated_at_descending(store):
    first = store.create("m")
    second = store.create("m")
    assert [s.id for s in store.list_all()] == [second.id, first.id]

    store.append_message(first.id, "user", "bump")
    assert [s.id for s in store.list_all()] == [first.id, second.id]


def test_first_user_message_sets_title_and_count(store):
    session = store.create("m")
    store.append_message(session.id, "user", "Hello there")
    store.append_message(session.id, "assistant", "Hi")
    store.append_message(session.id, "user", "Second question")
    updated = store.get(session.id)
    assert updated.title == "Hello there"
    assert updated.message_count == 3
    assert updated.updated_at > session.updated_at


def test_renamed_session_keeps_its_title(store):
    session = store.create("m")
    store.rename(session.id, "Mine")
    store.append_message(session.id, "user", "Hello there")
    assert store.get(session.id).title == "Mine"


def test_rename_unknown_session_raises(store):
    with pytest.raises(SessionNotFoundError):
        store.rename("missing", "x")


def test_title_from_message_folds_lines_and_cuts_with_ellipsis():
    assert title_from_message("a\n\n  b\tc") == "a b c"
    assert title_from_message("x" * 40) == "x" * 40
    assert title_from_message("x" * 41) == "x" * 40 + "…"


def test_messages_are_logged_as_jsonl(store, tmp_path):
    session = store.create("m")
    store.append_message(session.id, "user", "Zażółć **bold**\nline two")
    store.append_message(session.id, "assistant", "ok")

    lines = (tmp_path / "sessions" / f"{session.id}.jsonl").read_text("utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert set(first) == {"id", "ts", "role", "content"}
    assert first["content"] == "Zażółć **bold**\nline two"
    assert [m["role"] for m in store.messages(session.id)] == ["user", "assistant"]


def test_history_survives_a_new_store_on_the_same_dir(tmp_path):
    first_run = SessionStore(tmp_path)
    session = first_run.create("m")
    first_run.append_message(session.id, "user", "remember me")
    first_run.close()

    second_run = SessionStore(tmp_path)
    assert second_run.get(session.id).title == "remember me"
    assert second_run.get(session.id).message_count == 1
    assert second_run.messages(session.id)[0]["content"] == "remember me"


def test_delete_removes_row_and_log_file(store, tmp_path):
    session = store.create("m")
    store.append_message(session.id, "user", "x")
    log_path = tmp_path / "sessions" / f"{session.id}.jsonl"
    assert log_path.exists()

    store.delete(session.id)

    assert store.get(session.id) is None
    assert not log_path.exists()


def test_delete_unknown_session_raises(store):
    with pytest.raises(SessionNotFoundError):
        store.delete("missing")


def test_delete_while_turn_running_raises_and_keeps_data(store):
    session = store.create("m")
    assert store.try_begin_turn(session.id)
    with pytest.raises(SessionBusyError):
        store.delete(session.id)
    assert store.get(session.id) is not None

    store.end_turn(session.id)
    store.delete(session.id)


def test_only_one_turn_can_run_per_session(store):
    session = store.create("m")
    assert store.try_begin_turn(session.id)
    assert not store.try_begin_turn(session.id)
    store.end_turn(session.id)
    assert store.try_begin_turn(session.id)


def test_unknown_session_cannot_begin_a_turn(store):
    assert not store.try_begin_turn("missing")


@pytest.mark.parametrize("bad_id", ["../x", "a/b", "..", "a\\b", "x.jsonl", "", "a" * 65])
def test_path_traversal_ids_are_rejected_before_touching_the_filesystem(store, tmp_path, bad_id):
    for call in (
        lambda: store.get(bad_id),
        lambda: store.messages(bad_id),
        lambda: store.delete(bad_id),
        lambda: store.append_message(bad_id, "user", "x"),
        lambda: store.try_begin_turn(bad_id),
    ):
        with pytest.raises(InvalidSessionIdError):
            call()
    assert not (tmp_path / "x.jsonl").exists()
