import pytest

from backend.interactions import ANSWERED, CANCELLED, TIMEOUT, Resolution
from backend.tools.ask import ask_spec
from backend.tools.propose import propose_spec

ask, propose = ask_spec(), propose_spec()


def test_ask_is_an_interaction_and_not_an_approval():
    assert ask.requires_approval is False
    assert ask.interaction.kind == "question"
    assert ask.required_arguments == ["question"]


def test_ask_payload_has_question_and_options():
    assert ask.interaction.payload({"question": " Which? ", "options": ["a", "b"]}) == {
        "question": "Which?",
        "options": ["a", "b"],
    }
    assert ask.interaction.payload({"question": "Which?"}) == {"question": "Which?", "options": []}


@pytest.mark.parametrize(
    "arguments",
    [
        {"question": "Which?"},
        {"question": "Which?", "options": []},
        {"question": "?", "options": list("abcdef")},
    ],
)
def test_valid_ask_arguments(arguments):
    assert ask.validate_arguments(arguments) is None


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"question": " "}, "question"),
        ({"question": 4}, "question"),
        ({"question": "?", "options": list("abcdefg")}, "at most 6"),
        ({"question": "?", "options": "a"}, "list of strings"),
        ({"question": "?", "options": [1]}, "list of strings"),
    ],
)
def test_invalid_ask_arguments(arguments, message):
    assert message in ask.validate_arguments(arguments)


def test_ask_result_is_the_trimmed_answer():
    outcome = ask.interaction.result(Resolution(ANSWERED, {"answer": " blue \n"}))
    assert (outcome.ok, outcome.output) == (True, "blue")


@pytest.mark.parametrize("unanswered", [TIMEOUT, CANCELLED])
def test_ask_without_an_answer(unanswered):
    outcome = ask.interaction.result(Resolution(unanswered))
    assert (outcome.ok, outcome.output) == (False, "No answer from the user.")


def test_propose_payload_has_title_and_details():
    assert propose.interaction.kind == "proposal"
    assert propose.requires_approval is False
    assert propose.required_arguments == ["title", "details"]
    assert propose.interaction.payload({"title": " T ", "details": "# D"}) == {
        "title": "T",
        "details": "# D",
    }


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"title": "", "details": "d"}, "title"),
        ({"title": "x" * 121, "details": "d"}, "at most 120"),
        ({"title": "t", "details": " "}, "details"),
        ({"title": "t", "details": 1}, "details"),
    ],
)
def test_invalid_propose_arguments(arguments, message):
    assert message in propose.validate_arguments(arguments)


def test_title_at_the_limit_is_valid():
    assert propose.validate_arguments({"title": "x" * 120, "details": "d"}) is None


@pytest.mark.parametrize(
    ("answer", "output"),
    [
        ({"decision": "accept"}, "accepted"),
        ({"decision": "accept", "comment": " do it "}, "accepted: do it"),
        ({"decision": "reject", "comment": "too risky"}, "rejected: too risky"),
        ({"decision": "reject", "comment": ""}, "rejected"),
    ],
)
def test_propose_result_names_the_decision_and_comment(answer, output):
    decision = "accepted" if answer["decision"] == "accept" else "rejected"
    outcome = propose.interaction.result(Resolution(decision, answer))
    assert (outcome.ok, outcome.output) == (True, output)


@pytest.mark.parametrize("unanswered", [TIMEOUT, CANCELLED])
def test_propose_without_a_response_is_a_rejection(unanswered):
    outcome = propose.interaction.result(Resolution(unanswered))
    assert (outcome.ok, outcome.output) == (
        False,
        "No response from the user; treated as rejected.",
    )
