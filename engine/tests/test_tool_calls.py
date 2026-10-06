import pytest

from backend.agent.tool_calls import InvalidArgumentsError, ToolCall, ToolCallAccumulator
from backend.llm.base import ToolCallFragment as F


def accumulate(*fragments):
    accumulator = ToolCallAccumulator()
    for fragment in fragments:
        accumulator.add(fragment)
    return accumulator.calls()


def test_fragments_with_one_index_form_one_call():
    (call,) = accumulate(F(0, "c1", "shell", '{"a"'), F(0, arguments_fragment=": 1}"))
    assert (call.id, call.name, call.arguments()) == ("c1", "shell", {"a": 1})


def test_two_indexes_make_two_calls_in_start_order():
    calls = accumulate(F(0, "c1", "a"), F(1, "c2", "b"), F(0, arguments_fragment="{}"))
    assert [(c.id, c.name, c.arguments_json) for c in calls] == [("c1", "a", "{}"), ("c2", "b", "")]


def test_a_new_id_at_a_reused_index_starts_a_new_call():
    calls = accumulate(F(0, "c1", "a", "{}"), F(0, "c2", "b", "{}"))
    assert [c.id for c in calls] == ["c1", "c2"]


def test_missing_id_gets_a_generated_one():
    (call,) = accumulate(F(0, None, "a", "{}"))
    assert call.id.startswith("call_")


def test_empty_arguments_mean_no_arguments():
    assert ToolCall("c", "n", "").arguments() == {}


@pytest.mark.parametrize("raw", ["{nope", "[1]", '"text"'])
def test_invalid_arguments_raise(raw):
    with pytest.raises(InvalidArgumentsError):
        ToolCall("c", "n", raw).arguments()
