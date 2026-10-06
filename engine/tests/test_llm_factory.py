from backend.llm.aisuite_client import AisuiteLLM
from backend.llm.factory import build_llm, current_model_name
from backend.llm.fake import FakeLLM
from backend.settings_service import SettingsService


def test_fake_when_env_says_so(monkeypatch, tmp_path):
    monkeypatch.setenv("AD_LLM", "fake")
    assert isinstance(build_llm(SettingsService(tmp_path)), FakeLLM)
    assert current_model_name(SettingsService(tmp_path)) == "fake"


def test_real_provider_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("AD_LLM", raising=False)
    settings = SettingsService(tmp_path)
    assert isinstance(build_llm(settings), AisuiteLLM)
    assert current_model_name(settings) == "gemma4:12b"
