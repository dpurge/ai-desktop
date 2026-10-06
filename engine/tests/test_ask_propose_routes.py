from tests.conftest import AUTH
from tests.test_chat import create_session
from tests.test_tool_turn_routes import post_message, turn_answered_by


def answer(http, body):
    async def respond(interaction_id):
        response = await http.post(f"/interactions/{interaction_id}", headers=AUTH, json=body)
        assert response.status_code == 200

    return respond


async def test_ask_streams_events_in_order_and_persists(make_client):
    async with make_client() as http:
        session_id = await create_session(http)

        events = await turn_answered_by(
            http, session_id, "ask: Which color?", answer(http, {"answer": "blue"})
        )
        messages = (await http.get(f"/sessions/{session_id}", headers=AUTH)).json()["messages"]

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
    assert events[2][1]["kind"] == "question"
    assert events[4][1]["output"] == "blue"
    assert "blue" in "".join(data["text"] for name, data in events if name == "text_delta")
    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "assistant"]
    assert (messages[1]["tool_calls"][0]["function"]["name"], messages[2]["content"]) == (
        "ask",
        "blue",
    )


async def test_propose_streams_events_in_order(make_client):
    async with make_client() as http:
        session_id = await create_session(http)

        events = await turn_answered_by(
            http,
            session_id,
            "propose: Rename project",
            answer(http, {"decision": "accept", "comment": "ok"}),
        )

    names = [name for name, _ in events]
    assert names[:5] == [
        "turn_started",
        "tool_call",
        "interaction_required",
        "interaction_resolved",
        "tool_result",
    ]
    assert events[2][1]["kind"] == "proposal"
    assert events[2][1]["payload"]["title"] == "Rename project"
    assert events[3][1]["outcome"] == "accepted"
    assert events[4][1]["output"] == "accepted: ok"
    assert events[-1] == ("turn_done", {"reason": "completed"})


async def test_invalid_answers_are_422_and_leave_the_interaction_pending(make_client):
    async with make_client() as http:
        session_id = await create_session(http)
        responses = []

        async def probe(interaction_id):
            url = f"/interactions/{interaction_id}"
            for body in ({"answer": "  "}, {"decision": "accept"}, {"answer": "red"}):
                responses.append(await http.post(url, headers=AUTH, json=body))

        await turn_answered_by(http, session_id, "ask: Which color?", probe)

    assert [r.status_code for r in responses] == [422, 422, 200]
    assert "answer" in responses[0].json()["detail"]


async def test_invalid_proposal_answer_is_422(make_client):
    async with make_client() as http:
        session_id = await create_session(http)
        responses = []

        async def probe(interaction_id):
            url = f"/interactions/{interaction_id}"
            for body in ({"decision": "approve"}, {"decision": "reject", "comment": "x" * 2001}):
                responses.append(await http.post(url, headers=AUTH, json=body))
            await http.post(url, headers=AUTH, json={"decision": "reject"})

        await turn_answered_by(http, session_id, "propose: T", probe)

    assert [r.status_code for r in responses] == [422, 422]
    assert "accept" in responses[0].json()["detail"]
    assert "comment" in responses[1].json()["detail"]


async def test_tools_lists_every_tool_and_stubs_are_unavailable(client):
    response = await client.get("/tools", headers=AUTH)

    assert response.status_code == 200
    tools = {tool["name"]: tool for tool in response.json()}
    assert list(tools) == ["shell", "ask", "propose", "load_skill", "gmail", "gcal", "github"]
    assert tools["shell"]["requires_approval"] is True
    assert tools["ask"]["available"] is True
    assert all(tools[name]["available"] is False for name in ("gmail", "gcal", "github"))
    assert all(tool["enabled"] for tool in tools.values())


async def test_tools_reports_disabled_shell(make_client, tmp_path):
    (tmp_path / "config.toml").write_text("[tools.shell]\nenabled = false\n")
    async with make_client() as http:
        response = await http.get("/tools", headers=AUTH)

    assert response.json()[0] | {"description": ""} == {
        "name": "shell",
        "description": "",
        "requires_approval": True,
        "available": True,
        "enabled": False,
    }


async def test_tools_requires_the_token(client):
    assert (await client.get("/tools")).status_code == 401


async def test_ask_while_ask_unanswered_can_be_cancelled(make_client):
    async with make_client() as http:
        session_id = await create_session(http)

        async def cancel(_interaction_id):
            await http.post(f"/sessions/{session_id}/cancel", headers=AUTH)

        events = await turn_answered_by(http, session_id, "ask: Which color?", cancel)
        again = await post_message(http, session_id, "hello")

    assert events[-1] == ("turn_done", {"reason": "cancelled"})
    assert again.status_code == 200
