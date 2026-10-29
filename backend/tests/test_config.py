import pytest
from pydantic import ValidationError

from cvscore.config import Settings


def test_defaults(monkeypatch):
    monkeypatch.delenv("K_CONSUMERS", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "fake-key")

    settings = Settings(_env_file=None)

    assert settings.k_consumers == 2
    assert settings.llm_base_url == "http://localhost:11434/v1"


def test_env_var_overrides_default(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setenv("K_CONSUMERS", "7")

    settings = Settings(_env_file=None)

    assert settings.k_consumers == 7
    assert isinstance(settings.k_consumers, int)


def test_invalid_value_fails(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setenv("K_CONSUMERS", "otto")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_missing_api_key_fails(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
