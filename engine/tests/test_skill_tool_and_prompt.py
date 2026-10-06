from backend.agent.prompt import SYSTEM_PROMPT, build_system_prompt
from backend.config import Config, ProviderEndpoints
from backend.skills.loader import GLOBAL, Skill, SkillCatalog
from backend.tools.registry import ToolContext, registry_for

CONFIG = Config("ollama", "m", ProviderEndpoints("http://o", "http://r"))


def skill(name, body="Do it.", description="Does a thing"):
    return Skill(name, description, body, GLOBAL, path=None)


def catalog_of(*skills):
    return lambda: SkillCatalog(tuple(skills))


def offered(registry):
    return [schema["function"]["name"] for schema in registry.openai_schemas()]


async def run_load_skill(catalog, arguments):
    spec = registry_for(CONFIG, catalog).get("load_skill")
    return await spec.run(arguments, ToolContext(None))


async def test_load_skill_returns_the_body():
    outcome = await run_load_skill(catalog_of(skill("a", body="# A\n1. step")), {"name": "a"})

    assert (outcome.ok, outcome.output) == (True, "# A\n1. step")


async def test_unknown_skill_lists_what_is_available():
    outcome = await run_load_skill(catalog_of(skill("a"), skill("b")), {"name": "nope"})

    assert outcome.ok is False
    assert outcome.output == "No skill named 'nope'. Available: a, b"


async def test_load_skill_sees_skills_added_after_the_registry_was_built():
    skills = [skill("a")]
    registry = registry_for(CONFIG, lambda: SkillCatalog(tuple(skills)))
    skills.append(skill("later", body="Late body"))

    outcome = await registry.get("load_skill").run({"name": "later"}, ToolContext(None))

    assert outcome.output == "Late body"


async def test_oversize_body_is_capped():
    outcome = await run_load_skill(catalog_of(skill("a", body="x" * 100_000)), {"name": "a"})

    assert len(outcome.output) < 40_000
    assert outcome.output.endswith("[truncated]")


def test_load_skill_is_offered_only_when_a_skill_exists():
    assert "load_skill" in offered(registry_for(CONFIG, catalog_of(skill("a"))))
    assert "load_skill" not in offered(registry_for(CONFIG, catalog_of()))
    assert "load_skill" not in offered(registry_for(CONFIG))


def test_load_skill_needs_no_approval():
    assert registry_for(CONFIG, catalog_of(skill("a"))).get("load_skill").requires_approval is False


def test_prompt_lists_each_skill_and_tells_the_model_to_load_one():
    prompt = build_system_prompt(
        [skill("a", description="First"), skill("b", description="Second")]
    )

    assert prompt.startswith(SYSTEM_PROMPT)
    assert "## Skills" in prompt
    assert "load_skill" in prompt
    assert "- a: First\n- b: Second" in prompt


def test_prompt_has_no_skills_section_without_skills():
    assert build_system_prompt([]) == SYSTEM_PROMPT
