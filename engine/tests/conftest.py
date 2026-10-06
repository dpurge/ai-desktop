import httpx
import pytest

from backend.app import create_app
from backend.llm.fake import FakeLLM
from backend.secrets_store import SecretsStore
from backend.session_store import SessionStore
from backend.settings_service import SettingsService
from backend.tools.openshell import NOT_INSTALLED, OpenShellStatus

TOKEN = "test-token"
AUTH = {"X-AD-Token": TOKEN}


@pytest.fixture
def settings(tmp_path):
    # Empty env so a developer's OPENROUTER_API_KEY never changes test outcomes.
    return SettingsService(tmp_path, SecretsStore(tmp_path, env={}))


@pytest.fixture
def make_client(tmp_path, settings):
    def build(
        llm=None, gui_dir=None, http_transport=None, sandbox_status=None
    ) -> httpx.AsyncClient:
        app = create_app(
            token=TOKEN,
            session_store=SessionStore(tmp_path),
            settings=settings,
            http_transport=http_transport,
            gui_dir=gui_dir,
            llm=llm or FakeLLM(delay_s=0),
            # Fixed, so a developer's PATH never changes test outcomes.
            detect_sandbox=lambda: sandbox_status or OpenShellStatus(False, NOT_INSTALLED),
        )
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    return build


@pytest.fixture
async def client(make_client):
    async with make_client() as http:
        yield http
