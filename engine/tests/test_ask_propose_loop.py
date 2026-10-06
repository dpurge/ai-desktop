from backend.agent.loop import TurnServices, run_turn
from backend.agent.turns import Turn
from backend.config import Config, ProviderEndpoints
from backend.interactions import InteractionRegistry
from backend.llm.fake import FakeLLM
from backend.tools.registry import ToolContext, registry_for

# A concurrent answerer: the turn is an async generator, so the test replies from inside the
# event loop as soon as it sees the interaction_required event.


class Run:
    def __init__(self, text, answer=None, timeout_s=5):
        self.interactions = InteractionRegistry()
        self.turn = Turn()
        self.recorded: list[dict] = []
        self.events = []
        self._text, self._answer = text, answer
        self.services = TurnServices(
            llm=FakeLLM(delay_s=0),
            tools=registry_for(Config("ollama", "m", ProviderEndpoints("http://o", "http://r"))),
            tool_context=ToolContext(None),
            interactions=self.interactions,
            approval_timeout_s=timeout_s,
        )

    async def go(self):
        history = [{"role": "user", "content": self._text}]
        async for event in run_turn(self.services, self.turn, history, self.recorded.append):
            self.events.append(event)
            if event.name == "interaction_required" and self._answer:
                self._answer(self, event.data["interaction_id"])
        return self

    def event(self, name):
        return next(e.data for e in self.events if e.name == name)

    @property
    def names(self):
        return [e.name for e in self.events]

    @property
    def reply(self):
        return "".join(e.data["text"] for e in self.events if e.name == "text_delta")


def answer_with(body):
    return lambda run, interaction_id: run.interactions.resolve(interaction_id, body)


def cancel(run, _interaction_id):
    run.turn.cancel_event.set()
    run.interactions.cancel_all(run.turn.id)


async def test_ask_answered_flows_the_answer_to_the_model():
    run = await Run("ask: Which color?", answer_with({"answer": "blue"})).go()

    assert run.names[:5] == [
        "turn_started",
        "tool_call",
        "interaction_required",
        "interaction_resolved",
        "tool_result",
    ]
    required = run.event("interaction_required")
    assert required["kind"] == "question"
    assert required["tool"] == "ask"
    assert required["payload"] == {"question": "Which color?", "options": []}
    assert run.event("interaction_resolved")["outcome"] == "answered"
    result = run.event("tool_result")
    assert (result["ok"], result["output"]) == (True, "blue")
    assert run.reply == "The ask tool said: blue"
    assert run.events[-1].data == {"reason": "completed"}


async def test_ask_timeout_continues_the_turn_with_no_answer():
    run = await Run("ask: Which color?", timeout_s=0.02).go()

    assert run.event("interaction_resolved")["outcome"] == "timeout"
    assert run.event("tool_result")["output"] == "No answer from the user."
    assert run.reply == "The ask tool said: No answer from the user."
    assert run.events[-1].data == {"reason": "completed"}


async def test_propose_accepted_with_comment():
    run = await Run(
        "propose: Rename project", answer_with({"decision": "accept", "comment": "yes please"})
    ).go()

    required = run.event("interaction_required")
    assert required["kind"] == "proposal"
    assert required["payload"]["title"] == "Rename project"
    assert required["payload"]["details"]
    assert run.event("interaction_resolved")["outcome"] == "accepted"
    assert run.event("tool_result")["output"] == "accepted: yes please"
    assert run.reply == "The propose tool said: accepted: yes please"


async def test_propose_rejected():
    run = await Run("propose: Rename project", answer_with({"decision": "reject"})).go()

    assert run.event("interaction_resolved")["outcome"] == "rejected"
    assert run.event("tool_result")["output"] == "rejected"
    assert run.events[-1].data == {"reason": "completed"}


async def test_propose_timeout_is_treated_as_rejected():
    run = await Run("propose: Rename project", timeout_s=0.02).go()

    assert run.event("tool_result")["output"] == "No response from the user; treated as rejected."


async def test_cancel_while_waiting_for_an_answer_ends_the_turn():
    run = await Run("ask: Which color?", cancel).go()

    assert run.event("interaction_resolved")["outcome"] == "cancelled"
    assert run.events[-1].data == {"reason": "cancelled"}
    assert run.recorded[-1]["role"] == "tool"
    assert run.recorded[-1]["content"] == "No answer from the user."


async def test_tool_messages_are_recorded_for_both_tools():
    ask_run = await Run("ask: Which color?", answer_with({"answer": "blue"})).go()
    propose_run = await Run("propose: T", answer_with({"decision": "accept"})).go()

    for run, name, content in (
        (ask_run, "ask", "blue"),
        (propose_run, "propose", "accepted"),
    ):
        call, result, summary = run.recorded
        assert call["tool_calls"][0]["function"]["name"] == name
        assert result == {"role": "tool", "tool_call_id": "call_fake_1", "content": content}
        assert summary["content"] == f"The {name} tool said: {content}"


async def test_invalid_ask_arguments_are_a_tool_error_without_an_interaction():
    run = await Run("ask:").go()

    assert "interaction_required" not in run.names
    result = run.event("tool_result")
    assert result["ok"] is False
    assert "question" in result["output"]


async def test_stubs_are_never_offered_to_the_model():
    offered = []

    class Recording(FakeLLM):
        async def stream(self, messages, tools=None):
            offered.append([t["function"]["name"] for t in tools])
            async for delta in super().stream(messages, tools):
                yield delta

    run = Run("hello")
    run.services = TurnServices(**{**run.services.__dict__, "llm": Recording(delay_s=0)})
    await run.go()

    assert offered == [["shell", "ask", "propose"]]
