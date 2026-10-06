import dataclasses

import pytest

from backend.config import CONFIG_FILE_NAME, ConfigError, ShellConfig, load_config, save_config


def test_defaults_without_file(tmp_path):
    config = load_config(tmp_path)

    assert config.provider == "ollama"
    assert config.model == "gemma4:12b"
    assert config.endpoints.ollama_base_url == "http://localhost:11434"
    assert config.endpoints.openrouter_base_url == "https://openrouter.ai/api/v1"
    assert config.theme == "system"


def test_user_file_overrides_only_what_it_sets(tmp_path):
    (tmp_path / CONFIG_FILE_NAME).write_text('model = "m"\n[ollama]\nbase_url = "http://h:1"\n')

    config = load_config(tmp_path)

    assert config.model == "m"
    assert config.provider == "ollama"
    assert config.endpoints.ollama_base_url == "http://h:1"
    assert config.endpoints.openrouter_base_url == "https://openrouter.ai/api/v1"


def test_unknown_provider_has_actionable_message(tmp_path):
    (tmp_path / CONFIG_FILE_NAME).write_text('provider = "acme"\n')

    with pytest.raises(ConfigError, match=r"Unknown provider 'acme'.*ollama, openrouter"):
        load_config(tmp_path)


@pytest.mark.parametrize(
    "content",
    [
        'model = ""\n',
        "model = 3\n",
        '[ollama]\nbase_url = "ftp://x"\n',
        '[ui]\ntheme = "neon"\n',
        "not toml [",
    ],
)
def test_invalid_values_raise_config_error(tmp_path, content):
    (tmp_path / CONFIG_FILE_NAME).write_text(content)

    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_save_round_trip_and_no_temp_left(tmp_path):
    config = load_config(tmp_path)
    changed = dataclasses.replace(
        config, provider="openrouter", model="vendor/model:free", theme="dark"
    )

    save_config(tmp_path, changed)

    assert load_config(tmp_path) == changed
    assert [p.name for p in tmp_path.iterdir()] == [CONFIG_FILE_NAME]


def test_save_creates_missing_state_dir(tmp_path):
    state = tmp_path / "nested" / "state"

    save_config(state, load_config(state))

    assert (state / CONFIG_FILE_NAME).is_file()


def test_tool_and_approval_defaults(tmp_path):
    config = load_config(tmp_path)

    assert config.shell.enabled is True
    assert config.shell.cwd == "~"
    assert config.shell.timeout_s == 60
    assert config.approval_timeout_s == 600


def test_user_file_can_disable_shell_and_change_limits(tmp_path):
    (tmp_path / CONFIG_FILE_NAME).write_text(
        '[tools.shell]\nenabled = false\ncwd = "/work"\ntimeout_s = 5\n[approval]\ntimeout_s = 30\n'
    )

    config = load_config(tmp_path)

    assert (config.shell.enabled, config.shell.cwd, config.shell.timeout_s) == (False, "/work", 5)
    assert config.approval_timeout_s == 30


@pytest.mark.parametrize(
    "content",
    [
        '[tools.shell]\nenabled = "yes"\n',
        '[tools.shell]\ncwd = ""\n',
        "[tools.shell]\ntimeout_s = 0\n",
        "[tools.shell]\ntimeout_s = true\n",
        "[tools.shell]\ntimeout_s = 99999\n",
        '[approval]\ntimeout_s = "10"\n',
        "[approval]\ntimeout_s = -1\n",
    ],
)
def test_invalid_tool_settings_raise_config_error(tmp_path, content):
    (tmp_path / CONFIG_FILE_NAME).write_text(content)

    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_tool_settings_survive_a_save_round_trip(tmp_path):
    config = dataclasses.replace(
        load_config(tmp_path),
        shell=ShellConfig(enabled=False, cwd="/w", timeout_s=9),
        approval_timeout_s=42,
    )

    save_config(tmp_path, config)

    assert load_config(tmp_path) == config
