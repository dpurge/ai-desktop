import asyncio
from dataclasses import replace

from backend.agent.history import CANCELLED_TOOL_RESULT
from backend.agent.loop import Event, TurnServices, run_turn
from backend.agent.turns import Turn
from backend.config import ShellConfig
from backend.interactions import InteractionRegistry
from backend.llm.base import Delta, LLMError, ToolCallFragment
from backend.llm.fake import FakeLLM
from backend.tools.executor import ExecResult
from backend.tools.registry import ToolContext, ToolRegistry
from backend.tools.shell import shell_spec

USER_RUN = {"role": "user", "content": "run: echo hi"}


class FailingLLM:
    async def stream(self, messages, tools=None):
        raise LLMError("provider unreachable")
        yield  # unreachable; makes this an async generator like a real stream


class ScriptedExecutor:
    def __init__(self, result=None, delay_s=0.0):
        self.commands = []
        self.cancelled = False
        self._result = result or ExecResult(0, "hi\n", "", False)
        self._delay_s = delay_s

    async def run(self, command, cwd, timeout_s):
        self.commands.append(command)
        try:
            await asyncio.sleep(self._delay_s)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return self._result


class Harness:
    """A turn wired to a fake executor, answering approvals the way a test says."""

    def __init__(self, llm=None, executor=None, answer=None, timeout_s=5, shell_enabled=True):
        self.interactions = InteractionRegistry()
        self.executor = executor or ScriptedExecutor()
        specs = [shell_spec(ShellConfig())] if shell_enabled else []
        self.services = TurnServices(
            llm=llm or FakeLLM(delay_s=0),
            tools=ToolRegistry(specs),
            tool_context=ToolContext(self.executor),
            interactions=self.interactions,
            approval_timeout_s=timeout_s,
            max_steps=3,
        )
        self.turn = Turn()
        self.answer = answer
        self.history: list[dict] = []
        self.recorded: list[dict] = []

    async def run(self, history) -> list[Event]:
        self.history = list(history)
        events = []
        async for event in run_turn(self.services, self.turn, self.history, self.recorded.append):
            events.append(event)
            if event.name == "interaction_required" and self.answer:
                self.answer(self, event)
        return events


def approve(harness, event):
    harness.interactions.resolve(event.data["interaction_id"], {"decision": "approve"})


def deny(harness, event):
    harness.interactions.resolve(event.data["interaction_id"], {"decision": "deny"})


def cancel(harness, event):
    harness.turn.cancel_event.set()
    harness.interactions.cancel_all(harness.turn.id)


def names(events):
    return [e.name for e in events]


async def test_turn_without_tools_emits_started_deltas_then_done():
    harness = Harness()

    events = await harness.run([{"role": "user", "content": "hello there"}])

    assert names(events) == ["turn_started"] + ["text_delta"] * 4 + ["turn_done"]
    assert events[0].data == {"turn_id": harness.turn.id}
    assert "".join(e.data["text"] for e in events if e.name == "text_delta") == (
        "You said: hello there"
    )
    assert events[-1].data == {"reason": "completed"}
    assert harness.recorded == [{"role": "assistant", "content": "You said: hello there"}]


async def test_llm_failure_becomes_error_then_turn_done_error():
    events = await Harness(llm=FailingLLM()).run([USER_RUN])

    assert names(events) == ["turn_started", "error", "turn_done"]
    assert events[1].data == {"code": "llm_error", "message": "provider unreachable"}
    assert events[2].data == {"reason": "error"}


async def test_approved_shell_call_runs_and_the_model_summarizes():
    harness = Harness(answer=approve)

    events = await harness.run([USER_RUN])

    assert names(events)[:5] == [
        "turn_started",
        "tool_call",
        "interaction_required",
        "interaction_resolved",
        "tool_result",
    ]
    assert set(names(events)[5:-1]) == {"text_delta"}
    assert events[-1].data == {"reason": "completed"}
    required = events[2].data
    assert required["kind"] == "approval"
    assert required["tool"] == "shell"
    assert required["call_id"] == events[1].data["call_id"]
    assert required["payload"]["command"] == "echo hi"
    assert required["timeout_s"] == 5
    assert events[3].data["outcome"] == "approved"
    assert events[4].data["ok"] is True
    assert harness.executor.commands == ["echo hi"]


async def test_history_carries_tool_calls_and_results_in_openai_format():
    harness = Harness(answer=approve)

    await harness.run([USER_RUN])

    assistant_call, tool_result, summary = harness.recorded
    assert assistant_call["role"] == "assistant"
    (call,) = assistant_call["tool_calls"]
    assert call == {
        "id": "call_fake_1",
        "type": "function",
        "function": {"name": "shell", "arguments": '{"command": "echo hi"}'},
    }
    assert tool_result == {"role": "tool", "tool_call_id": "call_fake_1", "content": "hi"}
    assert summary["content"] == "The shell tool said: hi"
    assert harness.history[1:] == harness.recorded


async def test_denied_call_does_not_run_and_the_turn_continues():
    harness = Harness(answer=deny)

    events = await harness.run([USER_RUN])

    assert harness.executor.commands == []
    result = next(e for e in events if e.name == "tool_result")
    assert result.data["ok"] is False
    assert result.data["output"] == "The user denied this command."
    assert next(e for e in events if e.name == "interaction_resolved").data["outcome"] == "denied"
    assert events[-1].data == {"reason": "completed"}


async def test_unanswered_approval_times_out_as_a_denial():
    harness = Harness(timeout_s=0.02)

    events = await harness.run([USER_RUN])

    assert harness.executor.commands == []
    assert next(e for e in events if e.name == "interaction_resolved").data["outcome"] == "timeout"
    assert next(e for e in events if e.name == "tool_result").data["output"] == (
        "No response from the user; treated as denied."
    )
    assert events[-1].data == {"reason": "completed"}


async def test_cancel_while_awaiting_approval_ends_the_turn_and_answers_the_call():
    harness = Harness(answer=cancel)

    events = await harness.run([USER_RUN])

    assert next(e for e in events if e.name == "interaction_resolved").data["outcome"] == (
        "cancelled"
    )
    assert harness.executor.commands == []
    assert events[-1].data == {"reason": "cancelled"}
    assert harness.recorded[-1]["role"] == "tool"


async def test_cancel_while_the_tool_runs_stops_it():
    harness = Harness(executor=ScriptedExecutor(delay_s=30), answer=approve)
    asyncio.get_running_loop().call_later(0.1, harness.turn.cancel_event.set)

    events = await asyncio.wait_for(harness.run([USER_RUN]), timeout=5)

    assert harness.executor.cancelled is True
    assert events[-1].data == {"reason": "cancelled"}


class SlowLLM:
    async def stream(self, messages, tools=None):
        yield Delta(text="partial ")
        await asyncio.sleep(30)
        yield Delta(text="never")


async def test_cancel_while_streaming_keeps_the_partial_text():
    harness = Harness(llm=SlowLLM())
    asyncio.get_running_loop().call_later(0.1, harness.turn.cancel_event.set)

    events = await asyncio.wait_for(harness.run([USER_RUN]), timeout=5)

    assert events[-1].data == {"reason": "cancelled"}
    assert harness.recorded == [{"role": "assistant", "content": "partial "}]


class CallsToolLLM:
    """Calls the shell tool every round, with arguments chosen by the test."""

    def __init__(self, arguments_json):
        self._arguments_json = arguments_json

    async def stream(self, messages, tools=None):
        yield Delta(tool_calls=(ToolCallFragment(0, "c1", "shell", self._arguments_json),))


async def test_invalid_json_arguments_become_a_tool_error_not_a_crash():
    harness = Harness(llm=CallsToolLLM("{not json"), answer=approve)

    events = await harness.run([USER_RUN])

    result = next(e for e in events if e.name == "tool_result")
    assert result.data["ok"] is False
    assert "not valid JSON" in result.data["output"]
    assert "interaction_required" not in names(events)
    assert harness.executor.commands == []


async def test_missing_required_argument_is_a_tool_error():
    harness = Harness(llm=CallsToolLLM("{}"), answer=approve)

    events = await harness.run([USER_RUN])

    result = next(e for e in events if e.name == "tool_result")
    assert "Missing required argument(s) for shell: command" in result.data["output"]


async def test_unknown_tool_is_a_tool_error():
    harness = Harness(shell_enabled=False, llm=CallsToolLLM('{"command": "x"}'))

    events = await harness.run([USER_RUN])

    result = next(e for e in events if e.name == "tool_result")
    assert result.data["output"] == "Unknown tool: shell"


async def test_max_steps_ends_the_turn_with_that_reason():
    harness = Harness(llm=CallsToolLLM('{"command": "echo hi"}'), answer=approve)

    events = await harness.run([USER_RUN])

    assert names(events).count("tool_call") == 3
    assert events[-1].data == {"reason": "max_steps"}


async def test_shell_disabled_means_the_model_is_not_offered_the_tool():
    offered = []

    class RecordingLLM(FakeLLM):
        async def stream(self, messages, tools=None):
            offered.append(tools)
            async for delta in super().stream(messages, tools):
                yield delta

    harness = Harness(llm=RecordingLLM(delay_s=0), shell_enabled=False)

    events = await harness.run([USER_RUN])

    assert offered == [None]
    assert "tool_call" not in names(events)


async def test_tool_call_fragments_are_joined_across_deltas():
    class SplitCallLLM:
        async def stream(self, messages, tools=None):
            if messages[-1]["role"] == "tool":
                yield Delta(text="done")
                return
            yield Delta(tool_calls=(ToolCallFragment(0, "c1", "shell", '{"comm'),))
            yield Delta(tool_calls=(ToolCallFragment(0, arguments_fragment='and": "ls"}'),))

    harness = Harness(llm=SplitCallLLM(), answer=approve)

    await harness.run([USER_RUN])

    assert harness.executor.commands == ["ls"]


async def test_cancel_right_after_the_model_round_answers_the_announced_calls():
    class CancelsAfterCallLLM:
        def __init__(self, harness):
            self._harness = harness

        async def stream(self, messages, tools=None):
            yield Delta(tool_calls=(ToolCallFragment(0, "c1", "shell", '{"command": "ls"}'),))
            self._harness.turn.cancel_event.set()

    harness = Harness()
    harness.services = replace(harness.services, llm=CancelsAfterCallLLM(harness))

    events = await harness.run([USER_RUN])

    assert events[-1].data == {"reason": "cancelled"}
    assert harness.executor.commands == []
    assert [m["role"] for m in harness.recorded] == ["assistant", "tool"]
    assert harness.recorded[1] == {
        "role": "tool",
        "tool_call_id": "c1",
        "content": CANCELLED_TOOL_RESULT,
    }
