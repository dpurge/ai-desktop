from backend.llm.aisuite_client import AisuiteLLM
from tests.conftest import AUTH
from tests.test_aisuite_client import FakeClient, chunk
from tests.test_chat import create_session

KEY = "sk-test-not-real"


class RecordingFactory:
    """aisuite client factory that records each turn's provider config and hands out one client."""

    def __init__(self) -> None:
        self.client = FakeClient([chunk("ok")])
        self.provider_configs = []

    def __call__(self, provider_configs):
        self.provider_configs.append(provider_configs)
        return self.client


async def send(client, session_id) -> str:
    response = await client.post(
        f"/sessions/{session_id}/messages", headers=AUTH, json={"text": "hi"}
    )
    assert response.status_code == 200
    return response.text


async def test_saved_model_and_endpoint_apply_to_the_next_turn(make_client, settings):
    factory = RecordingFactory()
    async with make_client(llm=AisuiteLLM(settings, client_factory=factory)) as client:
        session_id = await create_session(client)
        await send(client, session_id)
        await client.put("/settings", headers=AUTH, json={"model": "llama3:8b"})
        await send(client, session_id)
        await client.put("/settings", headers=AUTH, json={"ollama": {"base_url": "http://b:1"}})
        await send(client, session_id)

    assert [call["model"] for call in factory.client.calls] == [
        "ollama:gemma4:12b",
        "ollama:llama3:8b",
        "ollama:llama3:8b",
    ]
    assert factory.provider_configs[-1]["ollama"]["base_url"] == "http://b:1"


async def test_saved_key_applies_to_the_next_turn(make_client, settings):
    factory = RecordingFactory()
    async with make_client(llm=AisuiteLLM(settings, client_factory=factory)) as client:
        await client.put("/settings", headers=AUTH, json={"provider": "openrouter"})
        session_id = await create_session(client)
        without_key = await send(client, session_id)
        await client.put(
            "/settings/api-key", headers=AUTH, json={"provider": "openrouter", "api_key": KEY}
        )
        with_key = await send(client, session_id)

    assert "OpenRouter API key is not set" in without_key
    assert "OpenRouter API key is not set" not in with_key
    assert factory.provider_configs[0]["openrouter"]["api_key"] == KEY
    assert KEY not in without_key + with_key
