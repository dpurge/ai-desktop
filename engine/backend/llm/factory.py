import os

from backend.llm.aisuite_client import AisuiteLLM
from backend.llm.base import LLM
from backend.llm.fake import FakeLLM
from backend.settings_service import SettingsService

LLM_ENV_VAR = "AD_LLM"


def build_llm(settings: SettingsService) -> LLM:
    if os.environ.get(LLM_ENV_VAR) == "fake":
        return FakeLLM()
    return AisuiteLLM(settings)


def current_model_name(settings: SettingsService) -> str:
    if os.environ.get(LLM_ENV_VAR) == "fake":
        return "fake"
    return settings.config().model
