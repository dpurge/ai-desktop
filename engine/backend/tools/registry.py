from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace

from backend.config import Config
from backend.interactions import Resolution
from backend.settings_service import SettingsService
from backend.skills.loader import SkillCatalog, skill_scanner
from backend.tools.executor import MAX_OUTPUT_BYTES, TRUNCATION_MARKER, Executor


@dataclass(frozen=True)
class ToolOutcome:
    ok: bool
    output: str

    @classmethod
    def capped(cls, ok: bool, output: str) -> "ToolOutcome":
        """Outcome whose text is cut to the output limit, so no tool can flood the model."""
        if len(output) > MAX_OUTPUT_BYTES:
            output = output[:MAX_OUTPUT_BYTES] + TRUNCATION_MARKER
        return cls(ok, output)


@dataclass(frozen=True)
class ToolContext:
    executor: Executor


ToolRun = Callable[[dict, ToolContext], Awaitable[ToolOutcome]]


async def _not_runnable(arguments: dict, context: ToolContext) -> ToolOutcome:
    raise NotImplementedError("This tool is answered through its interaction")


@dataclass(frozen=True)
class InteractionSpec:
    """How a tool whose whole job is to ask the user turns a call into an interaction."""

    kind: str
    payload: Callable[[dict], dict]  # what the card shows, from the call's arguments
    result: Callable[[Resolution], ToolOutcome]  # what the model is told, from the user's reply


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON schema of the arguments object
    requires_approval: bool
    run: ToolRun = _not_runnable
    # What the approval card shows for a call, e.g. {"command": ..., "cwd": ...}.
    approval_details: Callable[[dict], dict] = field(default=lambda arguments: {})
    # Checks argument values once the required ones are present; returns the problem, if any.
    validate_arguments: Callable[[dict], str | None] = field(default=lambda arguments: None)
    interaction: InteractionSpec | None = None
    # False for tools without a real implementation: listed to the user, never offered to a model.
    available: bool = True
    # False when the user switched the tool off in settings.
    enabled: bool = True

    @property
    def required_arguments(self) -> list[str]:
        return self.parameters.get("required", [])

    def openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self, specs: list[ToolSpec]) -> None:
        self._by_name = {spec.name: spec for spec in specs}

    def get(self, name: str) -> ToolSpec | None:
        """The tool a call may reach: a switched-off tool is unknown even if the model names it."""
        spec = self._by_name.get(name)
        return spec if spec is not None and spec.enabled else None

    def openai_schemas(self) -> list[dict]:
        return [
            spec.openai_schema()
            for spec in self._by_name.values()
            if spec.enabled and spec.available
        ]

    def describe(self) -> list[dict]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "requires_approval": spec.requires_approval,
                "available": spec.available,
                "enabled": spec.enabled,
            }
            for spec in self._by_name.values()
        ]


def default_registry(settings: SettingsService) -> ToolRegistry:
    """The tools offered right now; read per turn so config edits apply without a restart."""
    config = settings.config()
    return registry_for(config, skill_scanner(settings.state_dir, config.skills.workspace_dir))


def registry_for(
    config: Config, skill_catalog: Callable[[], SkillCatalog] | None = None
) -> ToolRegistry:
    """`skill_catalog` rescans the skills; without it the skill tool is left out."""
    # Imported here so shell.py can import the types above without a cycle.
    from backend.tools.ask import ask_spec
    from backend.tools.propose import propose_spec
    from backend.tools.shell import shell_spec
    from backend.tools.skill import skill_spec
    from backend.tools.stubs import stub_specs

    shell = replace(shell_spec(config.shell), enabled=config.shell.enabled)
    skill_tools = [skill_spec(skill_catalog)] if skill_catalog is not None else []
    return ToolRegistry([shell, ask_spec(), propose_spec(), *skill_tools, *stub_specs()])
