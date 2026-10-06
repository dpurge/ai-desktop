from backend.tools.registry import ToolContext, ToolOutcome, ToolSpec

# Connectors are out of scope for this version; these entries only reserve the names so the
# tool list can show them. They are never offered to the model.
_STUBS = {
    "gmail": "Read and send email through Gmail.",
    "gcal": "Read and create events in Google Calendar.",
    "github": "Work with GitHub repositories, issues and pull requests.",
}
_NO_ARGUMENTS = {"type": "object", "properties": {}}


def stub_specs() -> list[ToolSpec]:
    return [_stub_spec(name, description) for name, description in _STUBS.items()]


def _stub_spec(name: str, description: str) -> ToolSpec:
    async def run(arguments: dict, context: ToolContext) -> ToolOutcome:
        return ToolOutcome(False, f"{name} is not connected yet.")

    return ToolSpec(
        name=name,
        description=f"{description} Not connected yet: this is a placeholder.",
        parameters=_NO_ARGUMENTS,
        requires_approval=False,
        run=run,
        available=False,
    )
