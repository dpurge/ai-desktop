import json

import pytest

from backend.llm.fake import FakeLLM
from tests.conftest import AUTH


def parse_events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        name_line, data_line = block.split("\n")
        events.append(
            (name_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: ")))
        )
    return events


async def create_session(client) -> str:
    response = await client.post("/sessions", headers=AUTH)
    assert response.status_code == 201
    return response.json()["id"]


async def test_create_session_returns_id_and_title(client):
    response = await client.post("/sessions", headers=AUTH)
    body = response.json()
    assert len(body["id"]) == 32
    assert body["title"]


async def test_message_streams_deltas_then_turn_done(client):
    session_id = await create_session(client)

    response = await client.post(
        f"/sessions/{session_id}/messages", headers=AUTH, json={"text": "hello world"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_events(response.text)
    names = [name for name, _ in events]
    assert names[0] == "turn_started"
    assert names[-1] == "turn_done"
    assert set(names[1:-1]) == {"text_delta"}
    reply = "".join(data["text"] for name, data in events if name == "text_delta")
    assert reply == "You said: hello world"
    assert events[-1][1] == {"reason": "completed"}


async def test_second_turn_sees_history(make_client):
    seen: list[list[dict]] = []

    class RecordingLLM(FakeLLM):
        async def stream(self, messages, tools=None):
            seen.append([dict(m) for m in messages])
            async for delta in super().stream(messages, tools):
                yield delta

    async with make_client(llm=RecordingLLM(delay_s=0)) as http:
        session_id = await create_session(http)
        for text in ("one", "two"):
            await http.post(f"/sessions/{session_id}/messages", headers=AUTH, json={"text": text})

    # The system prompt leads the request but is not part of the stored history.
    assert [m["role"] for m in seen[1]] == ["system", "user", "assistant", "user"]


async def test_unknown_session_is_404(client):
    response = await client.post("/sessions/nope/messages", headers=AUTH, json={"text": "hi"})
    assert response.status_code == 404


@pytest.mark.parametrize("session_id", ["has.dot", "a" * 65, "bad%20id"])
async def test_invalid_session_id_is_422(client, session_id):
    response = await client.post(
        f"/sessions/{session_id}/messages", headers=AUTH, json={"text": "hi"}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("text", ["", "   "])
async def test_empty_text_is_422(client, text):
    session_id = await create_session(client)
    response = await client.post(
        f"/sessions/{session_id}/messages", headers=AUTH, json={"text": text}
    )
    assert response.status_code == 422


async def test_second_turn_while_running_is_409(client):
    session_id = await create_session(client)
    client._transport.app.state.session_store.try_begin_turn(session_id)

    response = await client.post(
        f"/sessions/{session_id}/messages", headers=AUTH, json={"text": "hi"}
    )

    assert response.status_code == 409


async def test_session_is_free_again_after_a_turn(client):
    session_id = await create_session(client)
    for _ in range(2):
        response = await client.post(
            f"/sessions/{session_id}/messages", headers=AUTH, json={"text": "hi"}
        )
        assert response.status_code == 200


async def test_text_over_the_limit_is_422_and_the_limit_itself_is_accepted(client):
    session_id = await create_session(client)
    url = f"/sessions/{session_id}/messages"

    too_long = await client.post(url, headers=AUTH, json={"text": "a" * 100_001})
    at_limit = await client.post(url, headers=AUTH, json={"text": "a" * 100_000})

    assert too_long.status_code == 422
    assert at_limit.status_code == 200
