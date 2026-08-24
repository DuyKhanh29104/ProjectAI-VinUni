from types import SimpleNamespace

import pytest

from src.services import agent_llm


class _Client:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _settings(**overrides):
    values = {
        "label_qa_llm_provider": "auto",
        "openai_api_key": "",
        "google_api_key": None,
        "model_name": "gpt-4o-mini",
        "google_model_name": "gemini-flash-latest",
        "llm_temperature": 0.7,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_auto_prefers_openai_when_both_keys_are_available(monkeypatch: pytest.MonkeyPatch):
    google_key = SimpleNamespace(get_secret_value=lambda: "gemini-key")
    monkeypatch.setattr(agent_llm, "get_settings", lambda: _settings(openai_api_key=" openai-key ", google_api_key=google_key))
    monkeypatch.setattr(agent_llm, "import_module", lambda name: SimpleNamespace(ChatOpenAI=_Client))

    client = agent_llm.get_agent_llm()

    assert client.kwargs["api_key"] == "openai-key"
    assert client.kwargs["model"] == "gpt-4o-mini"


def test_gemini_provider_uses_gemini_client(monkeypatch: pytest.MonkeyPatch):
    google_key = SimpleNamespace(get_secret_value=lambda: "gemini-key")
    monkeypatch.setattr(agent_llm, "get_settings", lambda: _settings(label_qa_llm_provider="gemini", google_api_key=google_key))
    monkeypatch.setattr(agent_llm, "import_module", lambda name: SimpleNamespace(ChatGoogleGenerativeAI=_Client))

    client = agent_llm.get_agent_llm()

    assert client.kwargs["google_api_key"] == "gemini-key"
    assert client.kwargs["model"] == "gemini-flash-latest"


def test_forced_openai_requires_its_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(agent_llm, "get_settings", lambda: _settings(label_qa_llm_provider="openai"))

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        agent_llm.get_agent_llm()
