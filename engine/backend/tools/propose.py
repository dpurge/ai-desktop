from backend.interactions import ACCEPTED, PROPOSAL, REJECTED, Resolution
from backend.tools.registry import InteractionSpec, ToolOutcome, ToolSpec

MAX_TITLE_CHARS = 120
NO_RESPONSE = "No response from the user; treated as rejected."

_DESCRIPTION = (
    "Put a plan or change to the user for acceptance before doing it. The user accepts or "
    "rejects it and may add a comment. Do not go ahead with a rejected proposal."
)
_PARAMETERS = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "maxLength": MAX_TITLE_CHARS,
            "description": "One-line summary of the proposal.",
        },
        "details": {"type": "string", "description": "The proposal itself, in Markdown."},
    },
    "required": ["title", "details"],
}


def propose_spec() -> ToolSpec:
    return ToolSpec(
        name="propose",
        description=_DESCRIPTION,
        parameters=_PARAMETERS,
        requires_approval=False,  # the proposal itself is what the user is asked
        validate_arguments=_validate,
        interaction=InteractionSpec(PROPOSAL, _payload, _result),
    )


def _validate(arguments: dict) -> str | None:
    title, details = arguments["title"], arguments["details"]
    if not isinstance(title, str) or not title.strip():
        return "The 'title' argument must be a non-empty string."
    if len(title.strip()) > MAX_TITLE_CHARS:
        return f"The 'title' argument must be at most {MAX_TITLE_CHARS} characters."
    if not isinstance(details, str) or not details.strip():
        return "The 'details' argument must be a non-empty string."
    return None


def _payload(arguments: dict) -> dict:
    return {"title": arguments["title"].strip(), "details": arguments["details"]}


def _result(resolution: Resolution) -> ToolOutcome:
    if resolution.outcome not in (ACCEPTED, REJECTED):
        return ToolOutcome(False, NO_RESPONSE)
    comment = (resolution.answer.get("comment") or "").strip()
    return ToolOutcome.capped(
        True, f"{resolution.outcome}: {comment}" if comment else resolution.outcome
    )
