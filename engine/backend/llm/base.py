from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


class LLMError(Exception):
    """A provider failure whose message is safe and readable enough to show to the user."""


@dataclass(frozen=True)
class ToolCallFragment:
    """One streamed piece of a tool call; pieces with the same index belong to one call."""

    index: int
    id: str | None = None
    name: str | None = None
    arguments_fragment: str = ""


@dataclass(frozen=True)
class Delta:
    text: str = ""
    tool_calls: tuple[ToolCallFragment, ...] = ()


class LLM(Protocol):
    def stream(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[Delta]:
        """Stream the assistant reply for an OpenAI-format message list.

        `tools` are OpenAI function schemas; None means the model is not offered any tool.
        """
        ...
