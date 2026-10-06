import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from importlib import resources
from pathlib import Path

logger = logging.getLogger(__name__)

SKILL_FILE_NAME = "SKILL.md"
MAX_BODY_BYTES = 32 * 1024
# Room for the frontmatter on top of the body, so a huge file is never read whole.
_MAX_HEADER_BYTES = 4 * 1024
_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_FENCE = "---"

BUILTIN, GLOBAL, WORKSPACE = "builtin", "global", "workspace"


class SkillError(Exception):
    """A SKILL.md is unusable; the message names the file and says what to fix."""


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    source: str  # BUILTIN, GLOBAL or WORKSPACE
    path: Path


@dataclass(frozen=True)
class SkillProblem:
    folder: str  # the folder's name only: the report may reach the GUI
    message: str


@dataclass(frozen=True)
class SkillCatalog:
    skills: tuple[Skill, ...] = ()
    problems: tuple[SkillProblem, ...] = ()

    def find(self, name: str) -> Skill | None:
        return next((skill for skill in self.skills if skill.name == name), None)


def parse_skill_text(text: str, label: str) -> tuple[str, str, str]:
    """Split SKILL.md text into (name, description, body); `label` names the file in errors.

    The file starts with a frontmatter block between two `---` lines, then a Markdown body.
    Supported frontmatter subset, so no YAML library is needed:
    - one `key: value` per line, split at the first colon;
    - a value may be wrapped in matching single or double quotes, which are removed;
    - blank lines and `#` comment lines are ignored; other keys are ignored;
    - `name` and `description` are required and must not be empty.
    """
    lines = text.lstrip("﻿").replace("\r\n", "\n").split("\n")
    if lines[0].strip() != _FENCE:
        raise SkillError(f"{label}: must start with a '---' frontmatter line.")
    try:
        closing = next(i for i in range(1, len(lines)) if lines[i].strip() == _FENCE)
    except StopIteration:
        raise SkillError(f"{label}: frontmatter is not closed by a second '---' line.") from None

    fields = _parse_fields(lines[1:closing], label)
    for required in ("name", "description"):
        if not fields.get(required):
            raise SkillError(f"{label}: frontmatter needs a non-empty '{required}'.")
    return fields["name"], fields["description"], "\n".join(lines[closing + 1 :]).strip()


def _parse_fields(lines: list[str], label: str) -> dict[str, str]:
    fields = {}
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator or not key.strip():
            raise SkillError(
                f"{label}: frontmatter line {line.strip()[:40]!r} is not 'key: value'."
            )
        fields[key.strip()] = _unquote(value.strip())
    return fields


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def load_skill_file(skill_file: Path, label: str, source: str) -> Skill:
    try:
        with skill_file.open("rb") as handle:
            raw = handle.read(MAX_BODY_BYTES + _MAX_HEADER_BYTES + 1)
    except OSError as exc:
        raise SkillError(f"{label}: cannot be read ({type(exc).__name__}).") from exc
    if len(raw) > MAX_BODY_BYTES + _MAX_HEADER_BYTES:
        raise SkillError(f"{label}: file is larger than {MAX_BODY_BYTES // 1024} KB.")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SkillError(f"{label}: must be UTF-8 text.") from exc
    name, description, body = parse_skill_text(text, label)
    if not _NAME_PATTERN.match(name):
        raise SkillError(
            f"{label}: name {name[:64]!r} must be lowercase letters, digits and '-', "
            "start with a letter or digit, and be at most 64 characters."
        )
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise SkillError(f"{label}: body is larger than {MAX_BODY_BYTES // 1024} KB.")
    return Skill(name, description, body, source, skill_file.parent)


def skill_roots(state_dir: Path, workspace_dir: str) -> list[tuple[str, Path]]:
    """Folders holding skill folders, lowest precedence first."""
    # Plain paths: the engine runs from files on disk (also when bundled with its data files).
    packaged = Path(str(resources.files("backend").joinpath("defaults", "skills")))
    roots = [(BUILTIN, packaged), (GLOBAL, state_dir / "skills")]
    if workspace_dir:
        roots.append((WORKSPACE, Path(workspace_dir).expanduser()))
    return roots


def discover_skills(roots: list[tuple[str, Path]]) -> SkillCatalog:
    """Scan every root; a later root overrides an earlier skill of the same name.

    A broken skill never raises: it is skipped, logged without its contents, and reported.
    Nothing is cached, so a folder dropped in is found by the next call.
    """
    by_name: dict[str, Skill] = {}
    problems: list[SkillProblem] = []
    for source, root in roots:
        if not root.is_dir():
            if source == WORKSPACE:
                problems.append(SkillProblem(root.name, "Workspace skills folder not found."))
            continue
        for folder in sorted(root.iterdir()):
            skill_file = folder / SKILL_FILE_NAME
            if not skill_file.is_file():
                continue
            try:
                skill = load_skill_file(skill_file, f"{folder.name}/{SKILL_FILE_NAME}", source)
            except SkillError as exc:
                logger.warning("Skipping %s skill: %s", source, exc)
                problems.append(SkillProblem(folder.name, str(exc)))
                continue
            by_name[skill.name] = skill
    return SkillCatalog(tuple(by_name.values()), tuple(problems))


def scan_skills(state_dir: Path, workspace_dir: str) -> SkillCatalog:
    return discover_skills(skill_roots(state_dir, workspace_dir))


def skill_scanner(state_dir: Path, workspace_dir: str) -> Callable[[], SkillCatalog]:
    """A fresh scan on every call, for code that must see skills added while it runs."""
    return partial(scan_skills, state_dir, workspace_dir)
