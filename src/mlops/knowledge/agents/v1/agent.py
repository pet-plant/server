"""Agent v1 — one shot at the whole probe set, with a validation repair loop.

Owner: TODO

```
knowledge/v1/generate-probes  (production label, or a pinned version)
      │  compiled with the document
      ▼
ChatPromptTemplate ─▶ ChatOpenAI.with_structured_output(GeneratedProbeSet)
      ▲                              │
      │  repair message              ▼
      └────────────── ValidationError / UngroundedProbeError
```

Structured output puts the JSON schema in the request, so the model is
constrained rather than merely asked; :mod:`mlops.knowledge.schemas` then
enforces the rules a JSON schema cannot express, and the grounding check
confirms every probe quotes the source document. **A set that never passes is
never returned** — :class:`ProbeGenerationError` is raised instead. There is no
"mostly valid" path out of this module.

The loop is a plain ``for``, not a graph: one prompt, one tool-free step, one
retry policy. A version that wants to plan, draft and criticise separately is a
different agent version with its own package — not a branch inside this one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_openai import ChatOpenAI
from langfuse import propagate_attributes
from langfuse.model import ChatPromptClient
from pydantic import ValidationError

from core.config import get_settings
from mlops.client import get_callback_handler, get_client
from mlops.knowledge.contract import (
    GenerateProbesInput,
    GenerateProbesResult,
    ProbeGenerationError,
    PromptRef,
)
from mlops.knowledge.schemas import GeneratedProbeSet, UngroundedProbeError
from mlops.settings import PRODUCTION_LABEL, Component

COMPONENT: Final = Component.KNOWLEDGE

VERSION: Final[str] = "v1"

#: The one prompt this version uses. Its text lives in ``prompts/generate-probes/``.
GENERATE_PROBES: Final[str] = f"knowledge/{VERSION}/generate-probes"

#: Attempts, including the first. Every retry after the first carries the
#: validation errors from the previous one, so it is a repair, not a re-roll.
DEFAULT_MAX_ATTEMPTS: Final[int] = 3

#: Probe generation is an offline authoring job, so a stale minute costs nothing
#: and a network round-trip per document does.
CACHE_TTL_SECONDS: Final[int] = 300


@dataclass(frozen=True)
class GenerationConfig:
    """Model hyper-parameters, read from the Langfuse prompt version's ``config``.

    Hyper-parameters belong to the prompt, not to this file and not to the
    environment: changing the temperature is a new prompt version, reviewable and
    revertible next to the text it was tuned against.

    ``model`` is therefore **required** — see :meth:`from_prompt_config`. The rest
    default, so a prompt authored with a bare ``{"model": …}`` still runs.
    """

    model: str
    temperature: float = 0.0
    max_tokens: int | None = None
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    #: Anything else in the prompt config, passed through to the client.
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_prompt_config(
        cls, config: Any, *, overrides: dict[str, Any] | None = None
    ) -> GenerationConfig:
        raw: dict[str, Any] = dict(config) if isinstance(config, dict) else {}
        raw.update(overrides or {})
        model = str(raw.pop("model", "") or "")
        if not model:
            # Deliberately no environment fallback. A default would mean the
            # model a run used is not recoverable from the prompt version it
            # names, and two runs of "v7" could differ by deployment — which
            # makes comparing versions meaningless. Fail instead.
            raise ValueError(
                "no model in the Langfuse prompt config: add `model` to the "
                "version's config (an experiment can pass it in `overrides`)"
            )
        return cls(
            model=model,
            temperature=float(raw.pop("temperature", 0.0)),
            max_tokens=raw.pop("max_tokens", None),
            max_attempts=max(1, int(raw.pop("max_attempts", DEFAULT_MAX_ATTEMPTS))),
            extra=raw,
        )


def _fetch_prompt(
    *, label: str | None, pins: Mapping[str, int] | None
) -> ChatPromptClient:
    """Resolve this version's prompt, by pinned version or by label."""
    pinned = (pins or {}).get(GENERATE_PROBES)
    kwargs: dict[str, Any] = {"type": "chat", "cache_ttl_seconds": CACHE_TTL_SECONDS}
    if pinned is not None:
        kwargs["version"] = pinned
        kwargs["cache_ttl_seconds"] = 0  # an experiment wants exactly this one
    else:
        kwargs["label"] = label or PRODUCTION_LABEL
    prompt = get_client(COMPONENT).get_prompt(GENERATE_PROBES, **kwargs)
    if not isinstance(prompt, ChatPromptClient):  # pragma: no cover - defensive
        raise TypeError(f"{GENERATE_PROBES} is a text prompt; it must be a chat prompt")
    return prompt


def _build_model(config: GenerationConfig) -> ChatOpenAI:
    """A chat client for the external, OpenAI-compatible text LLM."""
    settings = get_settings()
    if not settings.llm_api_base:
        raise ValueError("LLM_API_BASE is not set")
    return ChatOpenAI(
        model=config.model,
        temperature=config.temperature,
        max_completion_tokens=config.max_tokens,
        base_url=settings.llm_api_base,
        # Some OpenAI-compatible servers accept any key; the client still
        # insists on one being present.
        api_key=settings.llm_api_key or "unused",  # type: ignore[arg-type]
        # Whatever else the prompt config named (top_p, seed, …). LangChain
        # routes anything it does not recognise to `model_kwargs`.
        **config.extra,
    )


def _repair_message(error: Exception) -> HumanMessage:
    """Turn a validation failure into the next turn of the conversation."""
    if isinstance(error, ValidationError):
        detail = json.dumps(
            [
                {"field": ".".join(str(p) for p in e["loc"]), "problem": e["msg"]}
                for e in error.errors()
            ],
            ensure_ascii=False,
            indent=2,
        )
    else:
        detail = str(error)
    return HumanMessage(
        content=(
            "Your previous answer was rejected by validation. Fix exactly these "
            "problems and return the whole probe set again — do not apologise, "
            "do not explain, return only the corrected data.\n\n" + detail
        )
    )


def _run_with_repair(
    template: ChatPromptTemplate,
    model: Runnable[Any, Any],
    payload: GenerateProbesInput,
    config: GenerationConfig,
) -> tuple[GeneratedProbeSet, int]:
    """Call the model until its output validates, feeding failures back in.

    The template is rendered once; every retry replays those same messages with
    a repair instruction appended, so the model sees its original task *and*
    exactly what was wrong with its answer. Re-rendering instead would throw
    that away and just re-roll the dice.
    """
    messages: list[BaseMessage] = list(
        template.format_messages(**payload.as_prompt_variables())
    )
    invoke_config: RunnableConfig = {
        "callbacks": [get_callback_handler(COMPONENT)],
        "run_name": "generate-probes",
    }
    last_error: Exception | None = None

    for attempt in range(1, config.max_attempts + 1):
        try:
            result = model.invoke(messages, config=invoke_config)
            # `with_structured_output` already parses; re-validating is cheap and
            # makes this the single place where a set is declared acceptable.
            probe_set = GeneratedProbeSet.model_validate(result)
            probe_set.validate_against_document(payload.document_body)
        except (ValidationError, UngroundedProbeError) as exc:
            last_error = exc
            messages = [*messages, _repair_message(exc)]
            continue
        return probe_set, attempt

    raise ProbeGenerationError(
        config.max_attempts,
        last_error or RuntimeError("max_attempts must be at least 1"),
    )


class ProbeAgentV1:
    """Implements :class:`~mlops.knowledge.contract.ProbeAgent`."""

    # Not Final: the protocol declares plain attributes, and a read-only one
    # would not satisfy it.
    version: str = VERSION
    package_dir: Path = Path(__file__).parent

    def run(
        self,
        payload: GenerateProbesInput,
        *,
        label: str | None = PRODUCTION_LABEL,
        pins: Mapping[str, int] | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> GenerateProbesResult:
        prompt = _fetch_prompt(label=label, pins=pins)
        config = GenerationConfig.from_prompt_config(prompt.config, overrides=overrides)
        template = ChatPromptTemplate.from_messages(prompt.get_langchain_prompt())
        # Structured output puts the JSON schema in the request itself, so the
        # model is constrained rather than merely instructed.
        model = _build_model(config).with_structured_output(GeneratedProbeSet)

        client = get_client(COMPONENT)
        # One trace per document, with the repair rounds nested inside it as
        # generations. `propagate_attributes(prompt=…)` is what ties those
        # generations to the prompt version, which is how the Langfuse UI shows
        # a version's real-world behaviour next to its dataset runs.
        with (
            client.start_as_current_observation(
                name=f"knowledge.{VERSION}.generate_probes",
                as_type="chain",
                input={
                    "species_code": payload.species_code,
                    "title": payload.document_title,
                },
            ) as span,
            propagate_attributes(prompt=prompt),
        ):
            probe_set, attempts = _run_with_repair(template, model, payload, config)
            span.update(
                output={"probe_count": len(probe_set.probes), "attempts": attempts}
            )
            trace_id: str | None = span.trace_id

        return GenerateProbesResult(
            probe_set=probe_set,
            agent_version=VERSION,
            model=config.model,
            prompts=(PromptRef(prompt.name, prompt.version),),
            attempts=attempts,
            trace_id=trace_id,
        )


AGENT: Final = ProbeAgentV1()
