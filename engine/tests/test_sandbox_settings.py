import tomllib

from backend.config import CONFIG_FILE_NAME
from backend.tools.openshell import NOT_INSTALLED, NOT_WIRED, OpenShellStatus
from tests.conftest import AUTH
from tests.test_chat import create_session
from tests.test_tool_turn_routes import decision, turn_answered_by

READY = OpenShellStatus(True, "ready")  # a fake: no real status is available in this version


async def test_get_reports_enabled_available_and_reason(client):
    body = (await client.get("/settings", headers=AUTH)).json()
    assert body["sandbox"] == {"enabled": False, "available": False, "reason": NOT_INSTALLED}


async def test_enabling_while_unavailable_is_422_with_the_reason(client, tmp_path):
    response = await client.put("/settings", headers=AUTH, json={"sandbox": {"enabled": True}})
    assert response.status_code == 422
    assert response.json()["detail"] == NOT_INSTALLED
    assert not (tmp_path / CONFIG_FILE_NAME).exists()


async def test_disabling_is_always_allowed_and_persisted(client, tmp_path):
    response = await client.put("/settings", headers=AUTH, json={"sandbox": {"enabled": False}})
    assert response.status_code == 200
    assert response.json()["sandbox"]["enabled"] is False
    saved = tomllib.loads((tmp_path / CONFIG_FILE_NAME).read_text())
    assert saved["sandbox"] == {"enabled": False}


async def test_enabling_when_available_persists(make_client, tmp_path):
    async with make_client(sandbox_status=READY) as http:
        response = await http.put("/settings", headers=AUTH, json={"sandbox": {"enabled": True}})
    assert response.json()["sandbox"] == {"enabled": True, "available": True, "reason": "ready"}
    assert tomllib.loads((tmp_path / CONFIG_FILE_NAME).read_text())["sandbox"] == {"enabled": True}


async def test_other_updates_keep_the_sandbox_setting(make_client, tmp_path):
    async with make_client(sandbox_status=READY) as http:
        await http.put("/settings", headers=AUTH, json={"sandbox": {"enabled": True}})
        response = await http.put("/settings", headers=AUTH, json={"theme": "dark"})
    assert response.json()["sandbox"]["enabled"] is True


async def test_sandbox_must_be_a_real_boolean_with_no_extra_fields(client):
    for payload in ({"sandbox": {"enabled": "yes"}}, {"sandbox": {"enabled": True, "x": 1}}):
        response = await client.put("/settings", headers=AUTH, json=payload)
        assert response.status_code == 422


async def test_hand_edited_enabled_fails_closed_without_running_the_command(make_client, tmp_path):
    (tmp_path / CONFIG_FILE_NAME).write_text("[sandbox]\nenabled = true\n")
    marker = tmp_path / "should-not-exist"
    async with make_client(sandbox_status=OpenShellStatus(False, NOT_WIRED)) as http:
        session_id = await create_session(http)
        events = await turn_answered_by(
            http, session_id, f"run: touch {marker}", decision(http, "approve")
        )

    result = next(data for name, data in events if name == "tool_result")
    assert result["ok"] is False
    assert result["output"] == (
        "Sandbox is enabled but unavailable: OpenShell was found, but sandboxed execution is "
        "not wired up yet in this version. Disable it in Settings or fix the setup."
    )
    assert not marker.exists()


async def test_disabled_sandbox_still_runs_locally(make_client, tmp_path):
    marker = tmp_path / "ran"
    async with make_client() as http:
        session_id = await create_session(http)
        events = await turn_answered_by(
            http, session_id, f"run: touch {marker}", decision(http, "approve")
        )
    assert next(data for name, data in events if name == "tool_result")["ok"] is True
    assert marker.exists()
