import asyncio
import json
import re
from collections.abc import AsyncIterator

from backend.llm.base import Delta, ToolCallFragment

_WORD_WITH_TRAILING_SPACE = re.compile(r"\S+\s*")
RUN_PREFIX = "run:"
ASK_PREFIX = "ask:"
PROPOSE_PREFIX = "propose:"
SKILL_PREFIX = "skill:"
FAKE_CALL_ID = "call_fake_1"
_DEMO_PROPOSAL_DETAILS = "**Plan**\n\n1. Make the change.\n2. Check the result."


class FakeLLM:
    """Deterministic provider for demos and tests.

    - "run: <command>" as the last user message makes it call the shell tool once;
    - "ask: <question>" makes it call the ask tool with that question;
    - "propose: <title>" makes it call the propose tool with that title and a fixed plan;
    - "skill: <name>" makes it call the load_skill tool with that name;
    - a call is made only when its tool is offered;
    - once the tool result arrives it repeats the first line of that result in one sentence;
    - anything else is a canned reply, or an echo of the last user message.
    """

    def __init__(self, reply: str | None = None, delay_s: float = 0.03) -> None:
        self._reply = reply
        self._delay_s = delay_s

    async def stream(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> AsyncIterator[Delta]:
        demo_call = self._demo_call(messages, tools)
        if demo_call is not None:
            for fragment in _call_fragments(*demo_call):
                yield Delta(tool_calls=(fragment,))
            return
        # Splitting keeps whitespace attached to words so the deltas concatenate to the reply.
        for chunk in _WORD_WITH_TRAILING_SPACE.findall(self._reply_for(messages)):
            await asyncio.sleep(self._delay_s)
            yield Delta(text=chunk)

    def _demo_call(self, messages: list[dict], tools: list[dict] | None) -> tuple[str, dict] | None:
        last = messages[-1] if messages else {}
        if self._reply is not None or last.get("role") != "user":
            return None
        text = last["content"].strip()
        offered = {tool["function"]["name"] for tool in tools or []}
        for prefix, tool_name, build_arguments in _DEMOS:
            if text.startswith(prefix) and tool_name in offered:
                return tool_name, build_arguments(text.removeprefix(prefix).strip())
        return None

    def _reply_for(self, messages: list[dict]) -> str:
        if self._reply is not None:
            return self._reply
        last = messages[-1] if messages else {}
        if last.get("role") == "tool":
            tool_name = _tool_name_of_call(messages, last["tool_call_id"])
            return f"The {tool_name} tool said: {_first_line(last['content'])}"
        last_user_text = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return f"You said: {last_user_text.strip()}"


_DEMOS = (
    (RUN_PREFIX, "shell", lambda rest: {"command": rest}),
    (ASK_PREFIX, "ask", lambda rest: {"question": rest}),
    (PROPOSE_PREFIX, "propose", lambda rest: {"title": rest, "details": _DEMO_PROPOSAL_DETAILS}),
    (SKILL_PREFIX, "load_skill", lambda rest: {"name": rest}),
)


def _call_fragments(tool_name: str, arguments: dict) -> list[ToolCallFragment]:
    arguments_json = json.dumps(arguments)
    middle = len(arguments_json) // 2
    # Split in two so the engine's fragment accumulation is exercised by every demo.
    return [
        ToolCallFragment(0, FAKE_CALL_ID, tool_name, arguments_json[:middle]),
        ToolCallFragment(0, arguments_fragment=arguments_json[middle:]),
    ]


def _tool_name_of_call(messages: list[dict], call_id: str) -> str:
    for message in reversed(messages):
        for call in message.get("tool_calls", []):
            if call["id"] == call_id:
                return call["function"]["name"]
    return "requested"


def _first_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[0] if lines else "(empty)"
