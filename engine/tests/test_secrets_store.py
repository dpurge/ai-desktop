import os
import stat
import sys

import pytest

from backend.secrets_store import SECRETS_FILE_NAME, SecretsStore

KEY = "sk-or-very-secret-value"


def make_store(tmp_path, env=None):
    return SecretsStore(tmp_path, env={} if env is None else env)


def test_set_get_has_delete(tmp_path):
    store = make_store(tmp_path)
    assert not store.has_api_key("openrouter")

    store.set_api_key("openrouter", KEY)
    assert store.get_api_key("openrouter") == KEY
    assert store.has_api_key("openrouter")

    store.delete_api_key("openrouter")
    assert store.get_api_key("openrouter") is None


def test_delete_missing_key_is_noop(tmp_path):
    make_store(tmp_path).delete_api_key("openrouter")
    assert not (tmp_path / SECRETS_FILE_NAME).exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_file_is_owner_only_before_and_after_rewrite(tmp_path):
    store = make_store(tmp_path)
    path = tmp_path / SECRETS_FILE_NAME

    store.set_api_key("openrouter", KEY)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

    store.set_api_key("ollama", "other")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == [SECRETS_FILE_NAME]


def test_env_wins_over_file_for_openrouter(tmp_path):
    make_store(tmp_path).set_api_key("openrouter", "from-file")
    store = make_store(tmp_path, {"OPENROUTER_API_KEY": "from-env"})

    assert store.get_api_key("openrouter") == "from-env"


def test_env_does_not_apply_to_other_providers(tmp_path):
    store = make_store(tmp_path, {"OPENROUTER_API_KEY": "from-env"})
    assert store.get_api_key("ollama") is None


def test_repr_has_no_value(tmp_path):
    store = make_store(tmp_path)
    store.set_api_key("openrouter", KEY)
    assert KEY not in repr(store)


def test_empty_key_rejected_without_echo(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        make_store(tmp_path).set_api_key("openrouter", "  ")


def test_corrupt_file_error_does_not_quote_content(tmp_path):
    (tmp_path / SECRETS_FILE_NAME).write_text(f'{{"openrouter": "{KEY}"')

    with pytest.raises(ValueError) as caught:
        make_store(tmp_path).get_api_key("openrouter")

    assert KEY not in str(caught.value)
    assert caught.value.__cause__ is None
