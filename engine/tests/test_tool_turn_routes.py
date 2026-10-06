import asyncio

from backend.llm.fake import FakeLLM
from tests.conftest import AUTH
from tests.test_chat import create_session, parse_events

# The in-process transport returns a response only after the app finished it, so a test cannot
# react to a half-read stream. A concurrent task watches the engine's pending interactions
# instead and answers them while the turn request is still open.


async def post_message(http, session_id, text):
    return await http.post(f"/sessions/{session_id}/messages", headers=AUTH, json={"text": text})


async def turn_answered_by(http, session_id, text, respond):
    """Run a turn; `respond(interaction_id)` is awaited once its approval is pending."""
    interactions = http._transport.app.state.interactions

    async def responder():
        while not interactions.pending():
            await asyncio.sleep(0.01)
        await respond(interactions.pending()[0].id)

    helper = asyncio.create_task(responder())
    try:
        response = await asyncio.wait_for(post_message(http, session_id, text), timeout=10)
    finally:
        helper.cancel()
    await asyncio.gather(helper, return_exceptions=True)
    return parse_events(response.text)


def decision(http, value):
    async def respond(interaction_id):
        response = await http.post(
            f"/interactions/{interaction_id}", headers=AUTH, json={"decision": value}
        )
        assert response.status_code == 200

    return respond


async def test_approved_run_streams_events_in_order(make_client):
    async with make_client() as http:
        session_id = await create_session(http)

        events = await turn_answered_by(http, session_id, "run: echo hi", decision(http, "approve"))

    names = [name for name, _ in events]
    assert names[:5] == [
        "turn_started",
        "tool_call",
        "interaction_required",
        "interaction_resolved",
        "tool_result",
    ]
    assert set(names[5:-1]) == {"text_delta"}
    assert events[-1] == ("turn_done", {"reason": "completed"})
    result = events[4][1]
    assert (result["ok"], result["output"]) == (True, "hi")
    assert events[1][1]["arguments"] == {"command": "echo hi"}


async def test_denied_run_never_executes(make_client, tmp_path):
    marker = tmp_path / "ran"
    async with make_client() as http:
        session_id = await create_session(http)

        events = await turn_answered_by(
            http, session_id, f"run: touch {marker}", decision(http, "deny")
        )

    assert not marker.exists()
    assert dict(events)["tool_result"]["output"] == "The user denied this command."
    assert events[-1] == ("turn_done", {"reason": "completed"})


async def test_cancel_while_awaiting_approval(make_client):
    async with make_client() as http:
        session_id = await create_session(http)
        cancelled = []

        async def cancel(_interaction_id):
            response = await http.post(f"/sessions/{session_id}/cancel", headers=AUTH)
            cancelled.append(response.json())

        events = await turn_answered_by(http, session_id, "run: echo hi", cancel)
        after = await http.post(f"/sessions/{session_id}/cancel", headers=AUTH)
        again = await post_message(http, session_id, "hello")

    assert cancelled == [{"cancelled": True}]
    assert dict(events)["interaction_resolved"]["outcome"] == "cancelled"
    assert events[-1] == ("turn_done", {"reason": "cancelled"})
    assert after.json() == {"cancelled": False}
    assert again.status_code == 200  # the session was released


async def test_tool_messages_persist_and_reload(make_client):
    async with make_client() as http:
        session_id = await create_session(http)
        await turn_answered_by(http, session_id, "run: echo hi", decision(http, "approve"))

        messages = (await http.get(f"/sessions/{session_id}", headers=AUTH)).json()["messages"]

    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "assistant"]
    assert messages[1]["tool_calls"][0]["function"]["name"] == "shell"
    call_id = messages[1]["tool_calls"][0]["id"]
    assert (messages[2]["tool_call_id"], messages[2]["content"]) == (call_id, "hi")


async def test_next_turn_sends_tool_messages_to_the_model_in_openai_format(make_client):
    seen = []

    class RecordingLLM(FakeLLM):
        async def stream(self, messages, tools=None):
            seen.append(messages)
            async for delta in super().stream(messages, tools):
                yield delta

    async with make_client(llm=RecordingLLM(delay_s=0)) as http:
        session_id = await create_session(http)
        await turn_answered_by(http, session_id, "run: echo hi", decision(http, "approve"))
        await post_message(http, session_id, "thanks")

    last_request = seen[-1]
    assert [m["role"] for m in last_request] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "user",
    ]
    assert last_request[2]["tool_calls"][0]["type"] == "function"
    assert last_request[3]["tool_call_id"] == last_request[2]["tool_calls"][0]["id"]
    assert set(last_request[3]) == {"role", "tool_call_id", "content"}


async def test_disabled_shell_is_not_offered(make_client, tmp_path):
    (tmp_path / "config.toml").write_text("[tools.shell]\nenabled = false\n")
    async with make_client() as http:
        session_id = await create_session(http)

        response = await post_message(http, session_id, "run: echo hi")

    names = [name for name, _ in parse_events(response.text)]
    assert "tool_call" not in names
    assert names[-1] == "turn_done"


async def test_interaction_route_errors(make_client):
    async with make_client() as http:
        session_id = await create_session(http)
        statuses = []

        async def probe(interaction_id):
            url = f"/interactions/{interaction_id}"
            for decision_value in ("maybe", "approve", "approve"):
                response = await http.post(url, headers=AUTH, json={"decision": decision_value})
                statuses.append(response.status_code)

        await turn_answered_by(http, session_id, "run: echo hi", probe)
        unknown = await http.post("/interactions/nope", headers=AUTH, json={"decision": "approve"})
        not_object = await http.post("/interactions/x", headers=AUTH, json=["approve"])

    assert statuses == [422, 200, 404]
    assert unknown.status_code == 404
    assert not_object.status_code == 422


async def test_interactions_require_the_token(client):
    response = await client.post("/interactions/x", json={"decision": "approve"})
    assert response.status_code == 401


async def test_cancel_of_an_idle_session_is_false(client):
    session_id = await create_session(client)
    response = await client.post(f"/sessions/{session_id}/cancel", headers=AUTH)
    assert response.json() == {"cancelled": False}


async def test_a_second_turn_while_awaiting_approval_is_409(make_client):
    async with make_client() as http:
        session_id = await create_session(http)
        statuses = []

        async def try_second(_interaction_id):
            second = await post_message(http, session_id, "hi")
            statuses.append(second.status_code)
            await http.post(f"/sessions/{session_id}/cancel", headers=AUTH)

        await turn_answered_by(http, session_id, "run: echo hi", try_second)

    assert statuses == [409]
