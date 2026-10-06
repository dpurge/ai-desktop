import json
import logging

import pytest

from backend.session_log import SessionLog, SessionLogCorruptError
from tests.conftest import AUTH
from tests.test_chat import create_session

SESSION = "s1"


@pytest.fixture
def log(tmp_path):
    return SessionLog(tmp_path / "sessions")


def write_raw(log, content: bytes):
    (log._directory / f"{SESSION}.jsonl").write_bytes(content)


def raw(log) -> bytes:
    return (log._directory / f"{SESSION}.jsonl").read_bytes()


def test_a_corrupt_last_line_is_skipped_with_a_warning_that_has_no_content(log, caplog):
    write_raw(log, b'{"n": 1}\n{"n": 2, "secret": "do-not-log')

    with caplog.at_level(logging.WARNING):
        messages = log.read(SESSION)

    assert messages == [{"n": 1}]
    assert "line 2" in caplog.text
    assert f"{SESSION}.jsonl" in caplog.text
    assert "do-not-log" not in caplog.text


def test_a_last_line_cut_inside_a_multibyte_character_is_skipped(log):
    write_raw(log, b'{"n": 1}\n{"t": "' + "é".encode()[:1])

    assert log.read(SESSION) == [{"n": 1}]


def test_a_corrupt_line_before_the_last_still_raises_with_the_file_name_only(log):
    write_raw(log, b'{"n": 1}\nnot json\n{"n": 3}\n')

    with pytest.raises(SessionLogCorruptError) as raised:
        log.read(SESSION)

    assert "s1.jsonl line 2" in str(raised.value)
    assert str(log._directory) not in str(raised.value)


def test_append_after_a_partial_last_line_drops_the_fragment_and_stays_readable(log):
    write_raw(log, b'{"n": 1}\n{"n": 2, "tex')

    log.append(SESSION, {"n": 3})

    assert log.read(SESSION) == [{"n": 1}, {"n": 3}]
    assert raw(log) == b'{"n": 1}\n{"n": 3}\n'


def test_append_after_a_complete_last_line_without_newline_keeps_it(log):
    write_raw(log, b'{"n": 1}\n{"n": 2}')

    log.append(SESSION, {"n": 3})

    assert log.read(SESSION) == [{"n": 1}, {"n": 2}, {"n": 3}]


def test_append_to_a_normal_or_missing_file_is_unchanged(log):
    log.append(SESSION, {"n": 1})
    log.append(SESSION, {"n": 2})

    assert raw(log) == (json.dumps({"n": 1}) + "\n" + json.dumps({"n": 2}) + "\n").encode()


async def test_get_session_survives_a_truncated_last_line(client):
    session_id = await create_session(client)
    store = client._transport.app.state.session_store
    store.append_message(session_id, "user", "first")
    store.append_message(session_id, "assistant", "second")
    path = store._log._path(session_id)
    path.write_bytes(path.read_bytes()[:-15])

    response = await client.get(f"/sessions/{session_id}", headers=AUTH)

    assert response.status_code == 200
    assert [m["content"] for m in response.json()["messages"]] == ["first"]


async def test_a_corrupt_middle_line_is_a_readable_500_without_a_local_path(client):
    session_id = await create_session(client)
    store = client._transport.app.state.session_store
    store.append_message(session_id, "user", "first")
    store.append_message(session_id, "user", "second")
    path = store._log._path(session_id)
    first, second = path.read_bytes().splitlines()
    path.write_bytes(b"garbage\n" + first + b"\n" + second + b"\n")

    response = await client.get(f"/sessions/{session_id}", headers=AUTH)

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert f"{session_id}.jsonl line 1" in detail
    assert str(path.parent) not in detail
