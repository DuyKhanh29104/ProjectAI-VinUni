"""LLM client dedicated to Label QA explanations."""

from importlib import import_module
from typing import Any, cast

from langchain_openai import ChatOpenAI

from src.config import get_settings


def _get_google_chat_model_class() -> type[Any]:
    try:
        module = import_module("langchain_google_genai")
    except ImportError as error:
        raise RuntimeError(
            "langchain-google-genai is required when using GOOGLE_API_KEY. "
            "Install the agent-demo extras or set OPENAI_API_KEY instead."
        ) from error
    return cast(type[Any], getattr(module, "ChatGoogleGenerativeAI"))


def get_agent_llm() -> Any:
    settings = get_settings()
    openai_api_key = settings.openai_api_key.strip()
    google_api_key = settings.google_api_key.strip()
    provider = settings.llm_provider

    if provider == "openai" or (provider == "auto" and openai_api_key):
        if not openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        return ChatOpenAI(
            model=settings.model_name,
            api_key=openai_api_key,
            temperature=settings.llm_temperature,
        )

    if provider == "google" or (provider == "auto" and google_api_key):
        if not google_api_key:
            raise RuntimeError("GOOGLE_API_KEY is required when LLM_PROVIDER=google")
        google_chat_model = _get_google_chat_model_class()
        return google_chat_model(
            model=settings.model_name,
            google_api_key=google_api_key,
            temperature=settings.llm_temperature,
        )

    raise RuntimeError("OPENAI_API_KEY or GOOGLE_API_KEY is required for Label QA Agent explanations")
