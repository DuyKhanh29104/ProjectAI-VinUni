"""Configurable LLM client dedicated to Label QA explanations."""

from importlib import import_module
from typing import Any

from src.config import get_settings


def get_agent_llm() -> Any:
    settings = get_settings()
    provider = settings.label_qa_llm_provider

    # In auto mode OpenAI is selected first when both credentials are supplied.
    # This makes the active provider deterministic while allowing a Gemini
    # credential to remain configured as a simple fallback option.
    if provider in {"auto", "openai"} and settings.openai_api_key.strip():
        client_type = getattr(import_module("langchain_openai"), "ChatOpenAI")
        return client_type(
            model=settings.model_name,
            api_key=settings.openai_api_key.strip(),
            temperature=settings.llm_temperature,
        )

    if provider == "openai":
        raise RuntimeError("OPENAI_API_KEY is required when LABEL_QA_LLM_PROVIDER=openai")

    if provider in {"auto", "gemini"} and settings.google_api_key is not None:
        client_type = getattr(import_module("langchain_google_genai"), "ChatGoogleGenerativeAI")
        return client_type(
            model=settings.google_model_name,
            google_api_key=settings.google_api_key.get_secret_value(),
            temperature=settings.llm_temperature,
        )

    if provider == "gemini":
        raise RuntimeError("GOOGLE_API_KEY is required when LABEL_QA_LLM_PROVIDER=gemini")

    raise RuntimeError(
        "No Label QA LLM credential configured. Set OPENAI_API_KEY or GOOGLE_API_KEY, "
        "or use the built-in local explanation fallback."
    )
