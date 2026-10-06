import pytest

from backend.config import CONFIG_FILE_NAME, ConfigError, load_config


def test_sandbox_is_off_by_default(tmp_path):
    assert load_config(tmp_path).sandbox.enabled is False


def test_sandbox_enabled_must_be_a_boolean(tmp_path):
    (tmp_path / CONFIG_FILE_NAME).write_text('[sandbox]\nenabled = "yes"\n')
    with pytest.raises(ConfigError, match="sandbox.enabled"):
        load_config(tmp_path)
