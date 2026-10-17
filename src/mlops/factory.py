"""LLM client factory supporting Ollama and OpenAI providers.

OpenAI is the primary chat provider. When it is not available — no
``LLM_API_KEY``, or a call that cannot be completed — chat delegates to the
local Ollama model. ``LLM_PROVIDER=ollama`` skips OpenAI and uses Ollama only.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableConfig
from pydantic import BaseModel, ConfigDict

from core.config import Settings, get_settings
from mlops.settings import Component

logger = logging.getLogger(__name__)


def _openai_unavailable(error: BaseException) -> bool:
    """True when the OpenAI call cannot be completed and Ollama should run it."""
    import openai

    return isinstance(
        error,
        (
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.AuthenticationError,
            openai.PermissionDeniedError,
            openai.NotFoundError,
            openai.RateLimitError,
            openai.InternalServerError,
        ),
    )


class _DelegatedStructured(Runnable[LanguageModelInput, dict[str, Any] | BaseModel]):
    """Structured-output call that retries on Ollama when OpenAI is unavailable."""

    def __init__(self, primary: Runnable[Any, Any], fallback: Runnable[Any, Any]) -> None:
        self.primary = primary
        self.fallback = fallback

    def invoke(
        self,
        input: LanguageModelInput,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | BaseModel:
        try:
            return self.primary.invoke(input, config=config, **kwargs)
        except Exception as error:
            if not _openai_unavailable(error):
                raise
            logger.warning("OpenAI chat call failed (%s); delegating to Ollama", error)
            return self.fallback.invoke(input, config=config, **kwargs)


class OpenAIToOllamaChat(BaseChatModel):
    """Chat model that calls OpenAI, then Ollama if that call cannot be completed."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    primary: Any
    fallback: Any

    @property
    def _llm_type(self) -> str:
        return "openai-to-ollama"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            return self.primary._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        except Exception as error:
            if not _openai_unavailable(error):
                raise
            logger.warning("OpenAI chat call failed (%s); delegating to Ollama", error)
            return self.fallback._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def with_structured_output(
        self,
        schema: dict[str, Any] | type,
        *,
        include_raw: bool = False,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, dict[str, Any] | BaseModel]:
        return _DelegatedStructured(
            self.primary.with_structured_output(schema, include_raw=include_raw, **kwargs),
            self.fallback.with_structured_output(schema, include_raw=include_raw, **kwargs),
        )


def _ollama_chat(
    settings: Settings,
    *,
    temperature: float,
    model_override: str | None,
    max_tokens: int | None,
) -> BaseChatModel:
    from langchain_ollama import ChatOllama

    selected_model = model_override or settings.ollama_model or "llama3.2:latest"
    base_url = settings.ollama_host or "http://localhost:11434"
    logger.debug("Initializing ChatOllama: base_url=%s, model=%s", base_url, selected_model)
    ollama_kwargs: dict[str, Any] = {
        "base_url": base_url,
        "model": selected_model,
        "temperature": temperature,
    }
    if max_tokens is not None:
        ollama_kwargs["num_predict"] = max_tokens
    return ChatOllama(**ollama_kwargs)


def _openai_chat(
    settings: Settings,
    *,
    temperature: float,
    model_override: str | None,
    max_tokens: int | None,
) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    selected_model = model_override or settings.llm_model or "gpt-4o-mini"
    kwargs: dict[str, Any] = {
        "model": selected_model,
        "temperature": temperature,
        "api_key": settings.llm_api_key,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if settings.llm_api_base:
        kwargs["base_url"] = settings.llm_api_base
    logger.debug("Initializing ChatOpenAI: model=%s", selected_model)
    return ChatOpenAI(**kwargs)


def get_llm(
    component: Component | str | None = None,
    *,
    temperature: float = 0.2,
    model_override: str | None = None,
    max_tokens: int | None = None,
) -> BaseChatModel:
    """Return the chat model for this deployment.

    ``LLM_PROVIDER=ollama`` uses Ollama only. Otherwise OpenAI is primary.
    An empty ``LLM_API_KEY`` delegates immediately to ``OLLAMA_MODEL``. A set
    key still falls back to Ollama when the OpenAI call cannot be completed.
    A prompt ``model`` override applies to OpenAI only; the Ollama delegate
    always uses ``OLLAMA_MODEL``.
    """
    del component  # reserved for per-component tracing; selection is deployment-wide
    settings = get_settings()
    provider = (settings.llm_provider or "openai").lower().strip()
    if provider == "ollama":
        return _ollama_chat(
            settings,
            temperature=temperature,
            model_override=model_override,
            max_tokens=max_tokens,
        )

    ollama = _ollama_chat(
        settings,
        temperature=temperature,
        model_override=None,
        max_tokens=max_tokens,
    )
    if not (settings.llm_api_key or "").strip():
        logger.warning(
            "OpenAI is not available (LLM_API_KEY is empty); delegating to Ollama model %s",
            settings.ollama_model or "llama3.2:latest",
        )
        return ollama

    return OpenAIToOllamaChat(
        primary=_openai_chat(
            settings,
            temperature=temperature,
            model_override=model_override,
            max_tokens=max_tokens,
        ),
        fallback=ollama,
    )
