import pytest

from tests.conftest import AUTH
from tests.test_chat import create_session


async def test_list_is_empty_then_shows_created_sessions(client):
    assert (await client.get("/sessions", headers=AUTH)).json() == []
    first = await create_session(client)
    second = await create_session(client)

    listed = (await client.get("/sessions", headers=AUTH)).json()

    assert [s["id"] for s in listed] == [second, first]
    assert set(listed[0]) == {"id", "title", "model", "created_at", "updated_at", "message_count"}


async def test_create_with_title(client):
    response = await client.post("/sessions", headers=AUTH, json={"title": "  Plans  "})
    assert response.status_code == 201
    assert response.json()["title"] == "Plans"


async def test_get_returns_session_and_messages(client):
    session_id = await create_session(client)
    await client.post(f"/sessions/{session_id}/messages", headers=AUTH, json={"text": "hi there"})

    body = (await client.get(f"/sessions/{session_id}", headers=AUTH)).json()

    assert body["session"]["title"] == "hi there"
    assert body["session"]["message_count"] == 2
    assert [(m["role"], m["content"]) for m in body["messages"]] == [
        ("user", "hi there"),
        ("assistant", "You said: hi there"),
    ]


async def test_rename_trims_and_stops_auto_title(client):
    session_id = await create_session(client)
    response = await client.patch(
        f"/sessions/{session_id}", headers=AUTH, json={"title": "  Renamed  "}
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"

    await client.post(f"/sessions/{session_id}/messages", headers=AUTH, json={"text": "hello"})
    assert (await client.get(f"/sessions/{session_id}", headers=AUTH)).json()["session"][
        "title"
    ] == "Renamed"


async def test_delete_then_404(client):
    session_id = await create_session(client)
    assert (await client.delete(f"/sessions/{session_id}", headers=AUTH)).status_code == 204
    assert (await client.get(f"/sessions/{session_id}", headers=AUTH)).status_code == 404
    assert (await client.delete(f"/sessions/{session_id}", headers=AUTH)).status_code == 404


async def test_unknown_session_is_404_for_get_and_patch(client):
    assert (await client.get("/sessions/nope", headers=AUTH)).status_code == 404
    response = await client.patch("/sessions/nope", headers=AUTH, json={"title": "x"})
    assert response.status_code == 404


async def test_delete_with_running_turn_is_409(client):
    session_id = await create_session(client)
    client._transport.app.state.session_store.try_begin_turn(session_id)
    assert (await client.delete(f"/sessions/{session_id}", headers=AUTH)).status_code == 409


@pytest.mark.parametrize("session_id", ["has.dot", "a" * 65, "bad%20id"])
async def test_invalid_id_is_422(client, session_id):
    assert (await client.get(f"/sessions/{session_id}", headers=AUTH)).status_code == 422
    assert (await client.delete(f"/sessions/{session_id}", headers=AUTH)).status_code == 422
    patched = await client.patch(f"/sessions/{session_id}", headers=AUTH, json={"title": "x"})
    assert patched.status_code == 422


@pytest.mark.parametrize("title", ["", "   ", "x" * 121])
async def test_invalid_titles_are_422(client, title):
    session_id = await create_session(client)
    patched = await client.patch(f"/sessions/{session_id}", headers=AUTH, json={"title": title})
    created = await client.post("/sessions", headers=AUTH, json={"title": title})
    assert patched.status_code == 422
    assert created.status_code == 422


async def test_patch_without_title_is_422(client):
    session_id = await create_session(client)
    response = await client.patch(f"/sessions/{session_id}", headers=AUTH, json={})
    assert response.status_code == 422


async def test_failed_turn_without_text_stores_only_the_user_message(make_client):
    from tests.test_llm_error_event import RaisingLLM

    async with make_client(llm=RaisingLLM(RuntimeError("boom"))) as http:
        session_id = await create_session(http)
        await http.post(f"/sessions/{session_id}/messages", headers=AUTH, json={"text": "hi"})
        body = (await http.get(f"/sessions/{session_id}", headers=AUTH)).json()

    assert [m["role"] for m in body["messages"]] == ["user"]


async def test_partial_reply_is_stored_when_the_stream_fails(make_client):
    class FailsAfterText:
        async def stream(self, messages, tools=None):
            from backend.llm.base import Delta

            yield Delta(text="partial ")
            raise RuntimeError("boom")

    async with make_client(llm=FailsAfterText()) as http:
        session_id = await create_session(http)
        await http.post(f"/sessions/{session_id}/messages", headers=AUTH, json={"text": "hi"})
        body = (await http.get(f"/sessions/{session_id}", headers=AUTH)).json()
        again = await http.post(
            f"/sessions/{session_id}/messages", headers=AUTH, json={"text": "again"}
        )

    assert [(m["role"], m["content"]) for m in body["messages"]] == [
        ("user", "hi"),
        ("assistant", "partial "),
    ]
    assert again.status_code == 200  # the turn flag was released


async def test_new_session_records_the_configured_model(client):
    response = await client.post("/sessions", headers=AUTH)
    assert response.json()["model"] == "fake"
