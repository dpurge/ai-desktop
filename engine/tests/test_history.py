from backend.agent.history import CANCELLED_TOOL_RESULT, repair_tool_results
from backend.llm.fake import FakeLLM
from tests.conftest import AUTH
from tests.test_chat import create_session


def call(call_id):
    return {"id": call_id, "type": "function", "function": {"name": "shell", "arguments": "{}"}}


def assistant(*call_ids):
    return {"role": "assistant", "content": "", "tool_calls": [call(i) for i in call_ids]}


def tool(call_id, content="ok"):
    return {"role": "tool", "tool_call_id": call_id, "content": content}


USER = {"role": "user", "content": "hi"}
SYNTHETIC = {"role": "tool", "tool_call_id": "c1", "content": CANCELLED_TOOL_RESULT}


def test_a_complete_history_is_unchanged():
    messages = [USER, assistant("c1", "c2"), tool("c1"), tool("c2"), USER]
    assert repair_tool_results(messages) == messages


def test_unanswered_call_at_the_end_gets_a_cancelled_result():
    assert repair_tool_results([USER, assistant("c1")]) == [USER, assistant("c1"), SYNTHETIC]


def test_unanswered_call_before_the_next_message_gets_its_result_right_after_the_call():
    assert repair_tool_results([USER, assistant("c1"), USER]) == [
        USER,
        assistant("c1"),
        SYNTHETIC,
        USER,
    ]


def test_partially_answered_calls_keep_the_real_result_and_fill_the_rest():
    messages = [assistant("c1", "c2", "c3"), tool("c2", "real")]

    assert repair_tool_results(messages) == [
        assistant("c1", "c2", "c3"),
        SYNTHETIC,
        tool("c2", "real"),
        {**SYNTHETIC, "tool_call_id": "c3"},
    ]


def test_orphan_tool_messages_are_dropped():
    messages = [tool("x"), USER, assistant("c1"), tool("c1"), tool("unknown"), tool("c1", "again")]

    assert repair_tool_results(messages) == [USER, assistant("c1"), tool("c1")]


def test_a_result_separated_from_its_call_by_another_message_is_an_orphan():
    assert repair_tool_results([assistant("c1"), USER, tool("c1")]) == [
        assistant("c1"),
        SYNTHETIC,
        USER,
    ]


def test_the_input_is_not_modified():
    messages = [USER, assistant("c1")]
    repair_tool_results(messages)
    assert messages == [USER, assistant("c1")]


async def test_next_request_repairs_a_log_that_ends_in_an_unanswered_call(make_client):
    seen: list[list[dict]] = []

    class RecordingLLM(FakeLLM):
        async def stream(self, messages, tools=None):
            seen.append([dict(m) for m in messages])
            async for delta in super().stream(messages, tools):
                yield delta

    async with make_client(llm=RecordingLLM(delay_s=0)) as http:
        session_id = await create_session(http)
        store = http._transport.app.state.session_store
        store.append_message(session_id, "user", "run it")
        store.append_message(session_id, "assistant", "", {"tool_calls": [call("c1")]})
        stored_before = store.messages(session_id)

        await http.post(f"/sessions/{session_id}/messages", headers=AUTH, json={"text": "next"})
        shown = (await http.get(f"/sessions/{session_id}", headers=AUTH)).json()["messages"]

    assert [(m["role"], m.get("tool_call_id")) for m in seen[0][1:]] == [
        ("user", None),
        ("assistant", None),
        ("tool", "c1"),
        ("user", None),
    ]
    assert seen[0][3]["content"] == CANCELLED_TOOL_RESULT
    assert [m["role"] for m in shown] == ["user", "assistant", "user", "assistant"]
    assert shown[:2] == stored_before
