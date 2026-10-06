from collections.abc import Callable

from backend.skills.loader import SkillCatalog
from backend.tools.registry import ToolContext, ToolOutcome, ToolSpec

_DESCRIPTION = (
    "Load the full instructions of a skill listed in the system prompt. Call it when a skill "
    "matches the user's task, then follow the instructions it returns."
)
_PARAMETERS = {
    "type": "object",
    "properties": {"name": {"type": "string", "description": "The skill's name."}},
    "required": ["name"],
}


def skill_spec(skill_catalog: Callable[[], SkillCatalog]) -> ToolSpec:
    async def run(arguments: dict, context: ToolContext) -> ToolOutcome:
        name = arguments.get("name")
        # Scanned per call, so a skill added since the turn began can still be loaded.
        catalog = skill_catalog()
        skill = catalog.find(name) if isinstance(name, str) else None
        if skill is None:
            available = ", ".join(s.name for s in catalog.skills) or "none"
            return ToolOutcome(False, f"No skill named {name!r}. Available: {available}")
        return ToolOutcome.capped(True, skill.body)

    return ToolSpec(
        name="load_skill",
        description=_DESCRIPTION,
        parameters=_PARAMETERS,
        requires_approval=False,  # it only reads text the user installed
        run=run,
        # Nothing to load means nothing to offer the model.
        available=bool(skill_catalog().skills),
    )
