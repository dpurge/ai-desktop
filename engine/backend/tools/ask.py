from backend.interactions import ANSWERED, QUESTION, Resolution
from backend.tools.registry import InteractionSpec, ToolOutcome, ToolSpec

MAX_OPTIONS = 6
NO_ANSWER = "No answer from the user."

_DESCRIPTION = (
    "Ask the user a question and wait for the reply. Use it when you need information only "
    "the user has. Offer 'options' for likely answers; the user may still type their own."
)
_PARAMETERS = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "description": "The question to show the user."},
        "options": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": MAX_OPTIONS,
            "description": "Optional suggested answers, shown as buttons.",
        },
    },
    "required": ["question"],
}


def ask_spec() -> ToolSpec:
    return ToolSpec(
        name="ask",
        description=_DESCRIPTION,
        parameters=_PARAMETERS,
        requires_approval=False,  # the question itself is what the user is asked
        validate_arguments=_validate,
        interaction=InteractionSpec(QUESTION, _payload, _result),
    )


def _validate(arguments: dict) -> str | None:
    question = arguments["question"]
    if not isinstance(question, str) or not question.strip():
        return "The 'question' argument must be a non-empty string."
    options = arguments.get("options", [])
    if not isinstance(options, list) or not all(isinstance(item, str) for item in options):
        return "The 'options' argument must be a list of strings."
    if len(options) > MAX_OPTIONS:
        return f"The 'options' argument may have at most {MAX_OPTIONS} entries."
    return None


def _payload(arguments: dict) -> dict:
    return {"question": arguments["question"].strip(), "options": arguments.get("options", [])}


def _result(resolution: Resolution) -> ToolOutcome:
    if resolution.outcome == ANSWERED:
        return ToolOutcome.capped(True, resolution.answer["answer"].strip())
    return ToolOutcome(False, NO_ANSWER)
