import json
import uuid
from dataclasses import dataclass

from backend.llm.base import ToolCallFragment


class InvalidArgumentsError(ValueError):
    """The model sent tool arguments that are not a JSON object."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments_json: str

    def arguments(self) -> dict:
        try:
            parsed = json.loads(self.arguments_json or "{}")
        except json.JSONDecodeError as exc:
            raise InvalidArgumentsError(f"Arguments are not valid JSON: {exc.msg}") from None
        if not isinstance(parsed, dict):
            raise InvalidArgumentsError("Arguments must be a JSON object")
        return parsed

    def as_openai(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments_json},
        }


@dataclass
class _PartialCall:
    id: str | None = None
    name: str = ""
    arguments_json: str = ""


class ToolCallAccumulator:
    """Joins streamed fragments into whole calls, in the order the calls started."""

    def __init__(self) -> None:
        self._calls: list[_PartialCall] = []
        self._open_by_index: dict[int, _PartialCall] = {}

    def add(self, fragment: ToolCallFragment) -> None:
        call = self._open_by_index.get(fragment.index)
        # An id appears once per call, so a different id at a used index starts a new call.
        # Some local servers reuse one index for every call.
        if call is None or (fragment.id and call.id and fragment.id != call.id):
            call = _PartialCall()
            self._calls.append(call)
            self._open_by_index[fragment.index] = call
        call.id = call.id or fragment.id
        call.name += fragment.name or ""
        call.arguments_json += fragment.arguments_fragment

    def calls(self) -> list[ToolCall]:
        # Servers that give no id still need one, because the reply must reference it.
        return [
            ToolCall(call.id or f"call_{uuid.uuid4().hex[:12]}", call.name, call.arguments_json)
            for call in self._calls
        ]
