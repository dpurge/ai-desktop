import asyncio

import pytest

from backend.interactions import (
    InteractionRegistry,
    InvalidAnswerError,
    UnknownInteractionError,
)

PAYLOAD = {"tool": "shell", "command": "ls", "cwd": "/"}


def make(registry, turn_id="t1"):
    return registry.create("approval", PAYLOAD, turn_id)


async def test_approve_resolves_the_waiter():
    registry = InteractionRegistry()
    interaction = make(registry)
    waiter = asyncio.create_task(registry.await_answer(interaction, 5))

    registry.resolve(interaction.id, {"decision": "approve"})

    resolution = await waiter
    assert resolution.outcome == "approved"
    assert resolution.answer == {"decision": "approve"}
    assert len(interaction.id) == 32


async def test_deny_resolves_as_denied():
    registry = InteractionRegistry()
    interaction = make(registry)
    registry.resolve(interaction.id, {"decision": "deny"})
    assert (await registry.await_answer(interaction, 5)).outcome == "denied"


async def test_no_answer_times_out_and_is_no_longer_answerable():
    registry = InteractionRegistry()
    interaction = make(registry)

    resolution = await registry.await_answer(interaction, 0.02)

    assert resolution.outcome == "timeout"
    with pytest.raises(UnknownInteractionError):
        registry.resolve(interaction.id, {"decision": "approve"})


async def test_cancel_all_resolves_only_that_turn_as_cancelled():
    registry = InteractionRegistry()
    mine, other = make(registry, "t1"), make(registry, "t2")

    registry.cancel_all("t1")

    assert (await registry.await_answer(mine, 5)).outcome == "cancelled"
    registry.resolve(other.id, {"decision": "approve"})
    assert (await registry.await_answer(other, 5)).outcome == "approved"


async def test_second_answer_is_unknown():
    registry = InteractionRegistry()
    interaction = make(registry)
    registry.resolve(interaction.id, {"decision": "approve"})

    with pytest.raises(UnknownInteractionError):
        registry.resolve(interaction.id, {"decision": "deny"})


async def test_unknown_id_is_unknown():
    with pytest.raises(UnknownInteractionError):
        InteractionRegistry().resolve("0" * 32, {"decision": "approve"})


@pytest.mark.parametrize("answer", [{}, {"decision": "maybe"}, {"decision": 1}])
async def test_invalid_answer_is_rejected_and_the_interaction_stays_pending(answer):
    registry = InteractionRegistry()
    interaction = make(registry)

    with pytest.raises(InvalidAnswerError):
        registry.resolve(interaction.id, answer)

    registry.resolve(interaction.id, {"decision": "approve"})


async def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError, match="Unknown interaction kind"):
        InteractionRegistry().create("poll", {}, "t1")
