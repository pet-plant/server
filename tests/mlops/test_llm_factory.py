"""Tests for the multi-provider LLM factory (Ollama & OpenAI)."""

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from core.config import Settings
from mlops.factory import OpenAIToOllamaChat, get_llm
from mlops.settings import Component


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "local",
        "log_level": "INFO",
        "database_url": "sqlite://",
        "minio_endpoint": "localhost:9000",
        "minio_access_key": "minio",
        "minio_secret_key": "minio",
        "minio_secure": False,
        "minio_bucket_captures": "captures",
        "minio_bucket_frames_derived": "frames",
        "minio_bucket_eval_sets": "evals",
        "jwt_issuer": "pet-plant",
        "jwt_audience": "pet-plant-api",
        "jwt_alg": "HS256",
        "jwt_secret": "secret",
        "access_token_ttl_seconds": 3600,
        "admin_email": "admin@example.com",
        "admin_name": "Admin",
        "admin_password": "password",
        "llm_provider": "openai",
        "llm_model": "gpt-4o-mini",
        "ollama_host": "http://localhost:11434",
        "ollama_model": "qwen2.5:latest",
    }
    values.update(overrides)
    return Settings(**values)


def _auth_error() -> openai.AuthenticationError:
    response = httpx.Response(
        401, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    )
    return openai.AuthenticationError("invalid key", response=response, body=None)


def test_get_llm_openai_default():
    with patch("mlops.factory.get_settings", return_value=_settings(llm_api_key="sk-test")):
        model = get_llm(Component.ADVICE, temperature=0.3, model_override="gpt-4o")
        assert isinstance(model, OpenAIToOllamaChat)
        assert isinstance(model.primary, ChatOpenAI)
        assert model.primary.model_name == "gpt-4o"
        assert model.primary.temperature == 0.3
        assert isinstance(model.fallback, ChatOllama)
        assert model.fallback.model == "qwen2.5:latest"


def test_get_llm_delegates_to_ollama_when_openai_key_is_empty():
    with patch("mlops.factory.get_settings", return_value=_settings(llm_api_key="")):
        model = get_llm(Component.ADVICE, temperature=0.3, model_override="gpt-4o-mini")
        assert isinstance(model, ChatOllama)
        assert model.model == "qwen2.5:latest"
        assert model.base_url == "http://localhost:11434"
        assert model.temperature == 0.3


def test_get_llm_ollama_provider():
    with patch(
        "mlops.factory.get_settings",
        return_value=_settings(
            llm_provider="ollama",
            llm_api_key="sk-test",
            ollama_model="llama3.2:latest",
        ),
    ):
        model = get_llm(Component.COMPANION, temperature=0.7)
        assert isinstance(model, ChatOllama)
        assert model.model == "llama3.2:latest"
        assert model.base_url == "http://localhost:11434"
        assert model.temperature == 0.7


def test_openai_call_delegates_to_ollama_when_unavailable():
    fallback_result = ChatResult(generations=[ChatGeneration(message=AIMessage(content="local"))])
    primary = MagicMock()
    primary._generate.side_effect = _auth_error()
    fallback = MagicMock()
    fallback._generate.return_value = fallback_result
    model = OpenAIToOllamaChat(primary=primary, fallback=fallback)

    assert model._generate([]) is fallback_result
    fallback._generate.assert_called_once()


def test_openai_call_does_not_delegate_on_a_request_error():
    primary = MagicMock()
    primary._generate.side_effect = ValueError("bad prompt")
    fallback = MagicMock()
    model = OpenAIToOllamaChat(primary=primary, fallback=fallback)

    with pytest.raises(ValueError, match="bad prompt"):
        model._generate([])
    fallback._generate.assert_not_called()


def test_structured_output_delegates_when_openai_is_unavailable():
    primary_runnable = MagicMock()
    primary_runnable.invoke.side_effect = _auth_error()
    fallback_runnable = MagicMock()
    fallback_runnable.invoke.return_value = {"ok": True}
    primary = MagicMock()
    primary.with_structured_output.return_value = primary_runnable
    fallback = MagicMock()
    fallback.with_structured_output.return_value = fallback_runnable
    model = OpenAIToOllamaChat(primary=primary, fallback=fallback)

    assert model.with_structured_output(dict).invoke("plan") == {"ok": True}
    fallback_runnable.invoke.assert_called_once()
