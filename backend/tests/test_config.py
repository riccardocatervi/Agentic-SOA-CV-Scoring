import pytest
from pydantic import ValidationError

from cvscore.config import Settings


@pytest.fixture
def required_env(monkeypatch):
    """Set the two variables that have no default."""
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_MODEL", "fake-model")


def test_defaults(monkeypatch, required_env):
    monkeypatch.delenv("K_CONSUMERS", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.k_consumers == 2
    assert settings.llm_base_url == "http://localhost:11434/v1"


def test_env_var_overrides_default(monkeypatch, required_env):
    monkeypatch.setenv("K_CONSUMERS", "7")

    settings = Settings(_env_file=None)

    assert settings.k_consumers == 7
    assert isinstance(settings.k_consumers, int)


def test_invalid_value_fails(monkeypatch, required_env):
    monkeypatch.setenv("K_CONSUMERS", "otto")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("missing", ["LLM_API_KEY", "LLM_MODEL"])
def test_required_variable_missing_fails(monkeypatch, required_env, missing):
    monkeypatch.delenv(missing)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
