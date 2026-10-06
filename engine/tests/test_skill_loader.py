import pytest

from backend.skills.loader import (
    BUILTIN,
    GLOBAL,
    MAX_BODY_BYTES,
    WORKSPACE,
    SkillError,
    discover_skills,
    parse_skill_text,
    scan_skills,
)


def write_skill(root, folder, name=None, description="Does a thing", body="Steps.", raw=None):
    directory = root / folder
    directory.mkdir(parents=True, exist_ok=True)
    text = (
        raw
        if raw is not None
        else f"---\nname: {name or folder}\ndescription: {description}\n---\n{body}"
    )
    (directory / "SKILL.md").write_text(text, encoding="utf-8", newline="")
    return directory


def test_parses_name_description_and_body():
    text = "---\nname: demo\ndescription: Does a thing\n---\n# Title\n\n- one\n- two\n"

    assert parse_skill_text(text, "demo/SKILL.md") == (
        "demo",
        "Does a thing",
        "# Title\n\n- one\n- two",
    )


def test_quotes_are_removed_and_colons_in_values_are_kept():
    text = "---\nname: 'demo'\ndescription: \"Use when: asked\"\n---\nBody"

    name, description, _ = parse_skill_text(text, "x")

    assert (name, description) == ("demo", "Use when: asked")


def test_crlf_line_endings_are_accepted():
    text = "---\r\nname: demo\r\ndescription: Does a thing\r\n---\r\nLine one\r\nLine two\r\n"

    assert parse_skill_text(text, "x") == ("demo", "Does a thing", "Line one\nLine two")


def test_body_keeps_markdown_including_horizontal_rules():
    text = "---\nname: demo\ndescription: d\n---\n**bold**\n\n---\n\n`code`: yes\n"

    assert parse_skill_text(text, "x")[2] == "**bold**\n\n---\n\n`code`: yes"


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("---\ndescription: d\n---\nbody", "'name'"),
        ("---\nname: n\n---\nbody", "'description'"),
        ("---\nname: n\ndescription:   \n---\nbody", "'description'"),
        ("# Just markdown", "must start with"),
        ("---\nname: n\ndescription: d\nbody", "not closed"),
        ("---\nname n\n---\nbody", "key: value"),
    ],
)
def test_invalid_frontmatter_names_the_file(text, fragment):
    with pytest.raises(SkillError, match=r"demo/SKILL\.md.*" + fragment):
        parse_skill_text(text, "demo/SKILL.md")


def test_later_roots_override_earlier_skills_of_the_same_name(tmp_path):
    roots = []
    for source in (BUILTIN, GLOBAL, WORKSPACE):
        root = tmp_path / source
        write_skill(root, "shared", description=f"from {source}")
        roots.append((source, root))
    write_skill(tmp_path / BUILTIN, "only-builtin")

    catalog = discover_skills(roots)

    by_name = {skill.name: skill for skill in catalog.skills}
    assert by_name["shared"].source == WORKSPACE
    assert by_name["shared"].description == "from workspace"
    assert by_name["only-builtin"].source == BUILTIN
    assert catalog.problems == ()


def test_a_broken_skill_is_skipped_and_reported_without_hiding_others(tmp_path, caplog):
    write_skill(tmp_path, "good")
    write_skill(tmp_path, "broken", raw="no frontmatter SECRET-CONTENT")

    catalog = discover_skills([(GLOBAL, tmp_path)])

    assert [skill.name for skill in catalog.skills] == ["good"]
    assert [problem.folder for problem in catalog.problems] == ["broken"]
    assert "SECRET-CONTENT" not in caplog.text + catalog.problems[0].message
    assert str(tmp_path) not in catalog.problems[0].message


@pytest.mark.parametrize("name", ["Upper", "has space", "-leading", "a/b", "..", "x" * 65])
def test_invalid_names_are_rejected(tmp_path, name):
    write_skill(tmp_path, "folder", name=name)

    catalog = discover_skills([(GLOBAL, tmp_path)])

    assert catalog.skills == ()
    assert "name" in catalog.problems[0].message


def test_oversize_body_is_rejected(tmp_path):
    write_skill(tmp_path, "big", body="x" * (MAX_BODY_BYTES + 1))
    write_skill(tmp_path, "fits", body="x" * MAX_BODY_BYTES)

    catalog = discover_skills([(GLOBAL, tmp_path)])

    assert [skill.name for skill in catalog.skills] == ["fits"]
    assert "larger than 32 KB" in catalog.problems[0].message


def test_non_utf8_file_is_reported(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "SKILL.md").write_bytes(b"\xff\xfe\x00")

    catalog = discover_skills([(GLOBAL, tmp_path)])

    assert catalog.skills == ()
    assert "UTF-8" in catalog.problems[0].message


def test_folders_without_skill_file_and_missing_roots_are_ignored(tmp_path):
    (tmp_path / "notes").mkdir()

    catalog = discover_skills([(GLOBAL, tmp_path), (GLOBAL, tmp_path / "missing")])

    assert catalog == discover_skills([])


def test_missing_workspace_folder_is_reported(tmp_path):
    catalog = discover_skills([(WORKSPACE, tmp_path / "nowhere")])

    assert catalog.problems[0].folder == "nowhere"


def test_packaged_default_skill_is_found(tmp_path):
    catalog = scan_skills(tmp_path, "")

    skill = catalog.find("concise-summary")
    assert skill is not None
    assert skill.source == BUILTIN
    assert skill.description == "Summarize text or a conversation in a few short bullets"
    assert skill.body
    assert catalog.problems == ()


def test_scan_uses_state_dir_and_workspace_dir(tmp_path):
    workspace = tmp_path / "ws"
    write_skill(tmp_path / "state" / "skills", "mine")
    write_skill(workspace, "concise-summary", description="project version")

    catalog = scan_skills(tmp_path / "state", str(workspace))

    assert catalog.find("mine").source == GLOBAL
    assert catalog.find("concise-summary").description == "project version"


def test_rescan_finds_a_folder_added_later(tmp_path):
    assert scan_skills(tmp_path, "").find("late") is None

    write_skill(tmp_path / "skills", "late")

    assert scan_skills(tmp_path, "").find("late") is not None
