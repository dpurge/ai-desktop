import pytest

from tests.conftest import AUTH


async def test_missing_token_is_401(client):
    assert (await client.get("/health")).status_code == 401


async def test_wrong_token_is_401(client):
    response = await client.get("/health", headers={"X-AD-Token": "nope"})
    assert response.status_code == 401


async def test_good_token_is_200(client):
    response = await client.get("/health", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["ok"] is True


@pytest.mark.parametrize(
    "origin",
    [
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "http://localhost",
        "http://localhost:5173",
        "https://127.0.0.1:8443",
    ],
)
async def test_allowed_origin_passes(client, origin):
    response = await client.get("/health", headers={**AUTH, "Origin": origin})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize(
    "origin",
    ["https://evil.example", "http://localhost.evil.example", "http://127.0.0.1.evil.example"],
)
async def test_other_origin_is_403_even_with_token(client, origin):
    response = await client.get("/health", headers={**AUTH, "Origin": origin})
    assert response.status_code == 403


async def test_preflight_is_allowed_without_token(client):
    response = await client.options(
        "/sessions",
        headers={
            "Origin": "tauri://localhost",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-ad-token,content-type",
        },
    )
    assert response.status_code == 200
    assert "x-ad-token" in response.headers["access-control-allow-headers"].lower()


async def test_static_gui_is_public_but_api_is_not(make_client, tmp_path):
    (tmp_path / "index.html").write_text("<h1>gui</h1>")
    async with make_client(gui_dir=tmp_path) as http:
        assert (await http.get("/")).status_code == 200
        assert (await http.get("/health")).status_code == 401
        assert (await http.post("/sessions")).status_code == 401
