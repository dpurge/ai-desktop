import pytest

from backend.interactions import InteractionRegistry, InvalidAnswerError


def make(kind):
    registry = InteractionRegistry()
    return registry, registry.create(kind, {}, "t1")


async def test_question_answer_resolves_as_answered():
    registry, interaction = make("question")

    registry.resolve(interaction.id, {"answer": "  blue "})

    resolution = await registry.await_answer(interaction, 5)
    assert resolution.outcome == "answered"
    assert resolution.answer == {"answer": "  blue "}


@pytest.mark.parametrize(
    "answer", [{}, {"answer": ""}, {"answer": "   "}, {"answer": 3}, {"answer": "x" * 4001}]
)
async def test_invalid_question_answer_is_rejected_and_stays_pending(answer):
    registry, interaction = make("question")

    with pytest.raises(InvalidAnswerError, match="answer"):
        registry.resolve(interaction.id, answer)

    registry.resolve(interaction.id, {"answer": "ok"})


async def test_question_answer_at_the_length_limit_is_valid():
    registry, interaction = make("question")
    registry.resolve(interaction.id, {"answer": "x" * 4000})


@pytest.mark.parametrize(
    ("answer", "outcome"),
    [
        ({"decision": "accept"}, "accepted"),
        ({"decision": "reject"}, "rejected"),
        ({"decision": "accept", "comment": "go ahead"}, "accepted"),
        ({"decision": "reject", "comment": None}, "rejected"),
        ({"decision": "accept", "comment": "x" * 2000}, "accepted"),
    ],
)
async def test_proposal_decision_resolves(answer, outcome):
    registry, interaction = make("proposal")

    registry.resolve(interaction.id, answer)

    assert (await registry.await_answer(interaction, 5)).outcome == outcome


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        ({}, "decision"),
        ({"decision": "approve"}, "decision"),
        ({"decision": "accept", "comment": 5}, "comment"),
        ({"decision": "accept", "comment": "x" * 2001}, "comment"),
    ],
)
async def test_invalid_proposal_answer_is_rejected_and_stays_pending(answer, message):
    registry, interaction = make("proposal")

    with pytest.raises(InvalidAnswerError, match=message):
        registry.resolve(interaction.id, answer)

    registry.resolve(interaction.id, {"decision": "reject"})
