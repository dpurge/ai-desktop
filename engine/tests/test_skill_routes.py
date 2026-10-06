from backend.llm.fake import FakeLLM
from tests.conftest import AUTH
from tests.test_chat import create_session, parse_events
from tests.test_skill_loader import write_skill
from tests.test_tool_turn_routes import post_message


class RecordingLLM(FakeLLM):
    def __init__(self):
        super().__init__(reply="ok", delay_s=0)
        self.system_prompts = []

    async def stream(self, messages, tools=None):
        self.system_prompts.append(messages[0]["content"])
        async for delta in super().stream(messages, tools):
            yield delta


async def test_skills_route_requires_the_token(client):
    assert (await client.get("/skills")).status_code == 401


async def test_skills_route_lists_skills_and_problems_without_paths_or_bodies(
    make_client, tmp_path
):
    write_skill(tmp_path / "skills", "shout", description="Reply in capitals", body="SECRET BODY")
    write_skill(tmp_path / "skills", "broken", raw="nothing useful")
    async with make_client() as http:
        response = await http.get("/skills", headers=AUTH)

    body = response.json()
    assert response.status_code == 200
    assert body["skills"] == [
        {
            "name": "concise-summary",
            "description": "Summarize text or a conversation in a few short bullets",
            "source": "builtin",
        },
        {"name": "shout", "description": "Reply in capitals", "source": "global"},
    ]
    assert [problem["path"] for problem in body["problems"]] == ["broken"]
    assert "broken/SKILL.md" in body["problems"][0]["message"]
    assert str(tmp_path) not in response.text
    assert "SECRET BODY" not in response.text


async def test_skills_route_picks_up_a_folder_added_while_running(make_client, tmp_path):
    async with make_client() as http:
        before = (await http.get("/skills", headers=AUTH)).json()["skills"]
        write_skill(tmp_path / "skills", "fresh")
        after = (await http.get("/skills", headers=AUTH)).json()["skills"]

    assert "fresh" not in [skill["name"] for skill in before]
    assert "fresh" in [skill["name"] for skill in after]


async def test_skills_route_uses_the_configured_workspace_dir(make_client, tmp_path):
    workspace = tmp_path / "ws"
    write_skill(workspace, "project-only")
    (tmp_path / "config.toml").write_text(f'[skills]\nworkspace_dir = "{workspace}"\n')
    async with make_client() as http:
        skills = (await http.get("/skills", headers=AUTH)).json()["skills"]

    assert {"name": "project-only", "description": "Does a thing", "source": "workspace"} in skills


async def test_skill_demo_streams_call_then_result_then_reply(make_client):
    async with make_client() as http:
        session_id = await create_session(http)
        response = await post_message(http, session_id, "skill: concise-summary")
        messages = (await http.get(f"/sessions/{session_id}", headers=AUTH)).json()["messages"]

    events = parse_events(response.text)
    names = [name for name, _ in events]
    assert names[:3] == ["turn_started", "tool_call", "tool_result"]
    assert set(names[3:-1]) == {"text_delta"}
    assert events[-1] == ("turn_done", {"reason": "completed"})
    assert events[1][1]["name"] == "load_skill"
    assert events[2][1]["ok"] is True
    assert "Write at most 5 bullets" in events[2][1]["output"]
    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "assistant"]


async def test_skill_demo_with_unknown_name_reports_what_is_available(make_client):
    async with make_client() as http:
        session_id = await create_session(http)
        response = await post_message(http, session_id, "skill: nope")

    result = parse_events(response.text)[2][1]
    assert result["ok"] is False
    assert result["output"] == "No skill named 'nope'. Available: concise-summary"


async def test_system_prompt_lists_skills_and_is_not_stored(make_client, tmp_path):
    write_skill(tmp_path / "skills", "shout", description="Reply in capitals")
    llm = RecordingLLM()
    async with make_client(llm=llm) as http:
        session_id = await create_session(http)
        await post_message(http, session_id, "hello")
        messages = (await http.get(f"/sessions/{session_id}", headers=AUTH)).json()["messages"]

    assert "- shout: Reply in capitals" in llm.system_prompts[0]
    assert "- concise-summary:" in llm.system_prompts[0]
    assert all(m["role"] != "system" for m in messages)
