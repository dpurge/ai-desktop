from collections.abc import Sequence

from backend.skills.loader import Skill

SYSTEM_PROMPT = (
    "You are AI Desktop, an assistant running on the user's computer. "
    "You may use the tools provided to you when they help; the user approves commands before "
    "they run, so explain briefly what a command is for. "
    "Be concise."
)
_SKILLS_INTRO = (
    "Skills are reusable instructions. When one matches the task, call the load_skill tool "
    "with its name and follow what it returns. Available skills:"
)


def build_system_prompt(skills: Sequence[Skill]) -> str:
    if not skills:
        return SYSTEM_PROMPT
    listing = "\n".join(f"- {skill.name}: {skill.description}" for skill in skills)
    return f"{SYSTEM_PROMPT}\n\n## Skills\n{_SKILLS_INTRO}\n{listing}"


def with_system_prompt(history: list[dict], system_prompt: str = SYSTEM_PROMPT) -> list[dict]:
    """The request sent to the model; the prompt is never stored in the session log."""
    return [{"role": "system", "content": system_prompt}, *history]
