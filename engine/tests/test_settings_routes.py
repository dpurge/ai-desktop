import stat
import sys

import pytest

from backend.config import CONFIG_FILE_NAME
from backend.secrets_store import SECRETS_FILE_NAME
from backend.tools.openshell import NOT_INSTALLED
from tests.conftest import AUTH

KEY = "sk-test-not-real-value"


async def test_defaults(client):
    response = await client.get("/settings", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {
        "provider": "ollama",
        "model": "gemma4:12b",
        "ollama": {"base_url": "http://localhost:11434"},
        "openrouter": {"base_url": "https://openrouter.ai/api/v1"},
        "has_api_key": {"openrouter": False},
        "theme": "system",
        "sandbox": {"enabled": False, "available": False, "reason": NOT_INSTALLED},
    }


async def test_settings_require_the_token(client):
    assert (await client.get("/settings")).status_code == 401


async def test_partial_update_changes_only_what_is_sent_and_persists(client, tmp_path):
    response = await client.put(
        "/settings",
        headers=AUTH,
        json={"model": "llama3:8b", "theme": "dark", "ollama": {"base_url": "http://box:11434"}},
    )

    body = response.json()
    assert response.status_code == 200
    assert (body["provider"], body["model"], body["theme"]) == ("ollama", "llama3:8b", "dark")
    assert body["ollama"]["base_url"] == "http://box:11434"
    assert body["openrouter"]["base_url"] == "https://openrouter.ai/api/v1"
    assert (await client.get("/settings", headers=AUTH)).json() == body
    saved = (tmp_path / CONFIG_FILE_NAME).read_text()
    assert 'model = "llama3:8b"' in saved
    assert 'theme = "dark"' in saved


async def test_provider_can_be_switched(client):
    response = await client.put("/settings", headers=AUTH, json={"provider": "openrouter"})
    assert response.json()["provider"] == "openrouter"


@pytest.mark.parametrize(
    ("payload", "field", "hint"),
    [
        ({"provider": "acme"}, "provider", "ollama"),
        ({"model": "  "}, "model", ""),
        ({"theme": "neon"}, "theme", "system"),
        ({"ollama": {"base_url": "ftp://x"}}, "base_url", "http"),
        ({"openrouter": {"base_url": "not a url"}}, "base_url", "http"),
        ({"unknown_field": 1}, "unknown_field", ""),
    ],
)
async def test_invalid_updates_are_422_and_change_nothing(client, tmp_path, payload, field, hint):
    response = await client.put("/settings", headers=AUTH, json=payload)

    assert response.status_code == 422
    problems = response.json()["detail"]
    assert any(field in problem["loc"] for problem in problems)
    assert hint in str(problems)
    assert not (tmp_path / CONFIG_FILE_NAME).exists()


async def test_api_key_is_write_only(client, tmp_path):
    put = await client.put(
        "/settings/api-key", headers=AUTH, json={"provider": "openrouter", "api_key": KEY}
    )
    after_put = await client.get("/settings", headers=AUTH)
    after_update = await client.put("/settings", headers=AUTH, json={"theme": "light"})

    assert put.status_code == 204
    assert put.content == b""
    assert after_put.json()["has_api_key"] == {"openrouter": True}
    assert KEY not in after_put.text + after_update.text
    assert KEY not in (tmp_path / CONFIG_FILE_NAME).read_text()
    secrets_file = tmp_path / SECRETS_FILE_NAME
    # Windows has no POSIX permission bits; the mode is best-effort there.
    if not sys.platform.startswith("win"):
        assert stat.S_IMODE(secrets_file.stat().st_mode) == 0o600


async def test_api_key_can_be_deleted(client):
    await client.put(
        "/settings/api-key", headers=AUTH, json={"provider": "openrouter", "api_key": KEY}
    )

    deleted = await client.delete("/settings/api-key?provider=openrouter", headers=AUTH)

    assert deleted.status_code == 204
    assert (await client.get("/settings", headers=AUTH)).json()["has_api_key"] == {
        "openrouter": False
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"provider": "ollama", "api_key": KEY},
        {"provider": "openrouter", "api_key": "   "},
        {"provider": "openrouter"},
    ],
)
async def test_invalid_api_key_requests_are_422_without_echoing_the_key(client, payload):
    response = await client.put("/settings/api-key", headers=AUTH, json=payload)

    assert response.status_code == 422
    assert KEY not in response.text


async def test_delete_api_key_rejects_other_providers(client):
    response = await client.delete("/settings/api-key?provider=ollama", headers=AUTH)
    assert response.status_code == 422


async def test_unreadable_config_file_is_a_readable_500(client, tmp_path):
    (tmp_path / CONFIG_FILE_NAME).write_text("not toml [")

    response = await client.get("/settings", headers=AUTH)

    assert response.status_code == 500
    assert "Fix the file or delete it" in response.json()["detail"]


async def test_saving_settings_keeps_tool_settings(client, tmp_path):
    (tmp_path / "config.toml").write_text("[tools.shell]\nenabled = false\ntimeout_s = 9\n")

    response = await client.put("/settings", headers=AUTH, json={"theme": "dark"})

    assert response.status_code == 200
    saved = (tmp_path / "config.toml").read_text()
    assert "enabled = false" in saved
    assert "timeout_s = 9" in saved
