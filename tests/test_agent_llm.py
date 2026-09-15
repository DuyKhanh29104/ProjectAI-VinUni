import pytest

from src.services import agent_llm


class _Client:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_agent_uses_trimmed_openai_api_key(monkeypatch: pytest.MonkeyPatch):
    settings = type(
        "SettingsStub",
        (),
        {
            "llm_provider": "auto",
            "openai_api_key": " openai-key ",
            "google_api_key": "",
            "model_name": "gpt-4o-mini",
            "llm_temperature": 0.7,
        },
    )()
    monkeypatch.setattr(agent_llm, "get_settings", lambda: settings)
    monkeypatch.setattr(agent_llm, "ChatOpenAI", _Client)

    client = agent_llm.get_agent_llm()

    assert client.kwargs["api_key"] == "openai-key"
    assert client.kwargs["model"] == "gpt-4o-mini"


def test_agent_uses_google_api_key_when_openai_is_missing(monkeypatch: pytest.MonkeyPatch):
    settings = type(
        "SettingsStub",
        (),
        {
            "llm_provider": "auto",
            "openai_api_key": "  ",
            "google_api_key": " google-key ",
            "model_name": "gemini-1.5-flash",
            "llm_temperature": 0.7,
        },
    )()
    monkeypatch.setattr(agent_llm, "get_settings", lambda: settings)
    monkeypatch.setattr(agent_llm, "_get_google_chat_model_class", lambda: _Client)

    client = agent_llm.get_agent_llm()

    assert client.kwargs["google_api_key"] == "google-key"
    assert client.kwargs["model"] == "gemini-1.5-flash"


def test_agent_requires_any_llm_api_key(monkeypatch: pytest.MonkeyPatch):
    settings = type(
        "SettingsStub",
        (),
        {
            "llm_provider": "auto",
            "openai_api_key": "  ",
            "google_api_key": "",
            "model_name": "gpt-4o-mini",
            "llm_temperature": 0.7,
        },
    )()
    monkeypatch.setattr(agent_llm, "get_settings", lambda: settings)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY or GOOGLE_API_KEY"):
        agent_llm.get_agent_llm()
