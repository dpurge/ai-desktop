from backend.llm.base import LLMError
from tests.conftest import AUTH
from tests.test_chat import create_session, parse_events

SECRET = "sk-or-very-secret-value"


class RaisingLLM:
    def __init__(self, error):
        self._error = error

    async def stream(self, messages, tools=None):
        raise self._error
        yield


async def run_message(make_client, error):
    async with make_client(llm=RaisingLLM(error)) as http:
        session_id = await create_session(http)
        response = await http.post(
            f"/sessions/{session_id}/messages", headers=AUTH, json={"text": "hi"}
        )
    return response.text, parse_events(response.text)


async def test_llm_error_reaches_user_as_error_event(make_client):
    _, events = await run_message(make_client, LLMError("Cannot reach Ollama at http://h:1"))

    assert [name for name, _ in events] == ["turn_started", "error", "turn_done"]
    assert events[1][1]["message"] == "Cannot reach Ollama at http://h:1"
    assert events[2][1] == {"reason": "error"}


async def test_unexpected_error_does_not_leak_its_message(make_client):
    body, events = await run_message(make_client, RuntimeError(f"key was {SECRET}"))

    assert SECRET not in body
    assert "RuntimeError" in events[1][1]["message"]
    assert events[2][1] == {"reason": "error"}
