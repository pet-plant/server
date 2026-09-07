"""Execution code for ``knowledge`` — probe generation from a research document.

Owner: TODO

Offline authoring, not the request path: ``src/knowledge`` calls this when
someone generates a probe set for a species, then stores the result as a draft
and puts it through its own human approval.

**Ownership split.** MLOps owns *how the model is asked* — the prompt version and
its hyper-parameters. ``knowledge`` owns *what comes out* — the probes, their
approval, the one-approved-set-per-species rule and staleness tracking. Nothing
here approves anything.

Inputs are plain values — ``mlops`` must not import a bounded context, so the
calling context flattens its own models onto :class:`GenerateProbesInput`.

## The agent

A generate → validate → repair loop, built from LangChain runnables:

```
Langfuse prompt (production label)
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

The loop is a plain ``for``, not a graph: there is one tool-free step and one
retry policy. Reach for ``langgraph`` when a branch actually appears.

## Text only

The research document and the generated probes are text; no plant imagery is
ever sent to the external LLM. That is a property of this call site, so keep it:
:class:`GenerateProbesInput` has no image field and must not grow one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Final

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_openai import ChatOpenAI
from langfuse import propagate_attributes
from pydantic import ValidationError

from core.config import get_settings
from mlops.client import get_callback_handler, get_client
from mlops.knowledge import prompts
from mlops.knowledge.schemas import GeneratedProbeSet, UngroundedProbeError
from mlops.settings import PRODUCTION_LABEL, Component

COMPONENT: Final = Component.KNOWLEDGE

#: Attempts, including the first. Every retry after the first carries the
#: validation errors from the previous one, so it is a repair, not a re-roll.
DEFAULT_MAX_ATTEMPTS: Final[int] = 3


class ProbeGenerationError(RuntimeError):
    """Raised when no attempt produced a set that passes validation.

    Carries the last failure so a human reading the job log can tell a prompt
    problem (the same rule fails every time) from a flaky model.
    """

    def __init__(self, attempts: int, last_error: Exception) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"probe generation failed validation after {attempts} attempt(s): "
            f"{last_error}"
        )


@dataclass(frozen=True)
class GenerateProbesInput:
    """What ``src/knowledge`` passes in.

    ``document_body`` is the research text **verbatim** — the model quotes it
    back as ``evidence_quote``, the grounding check matches against this exact
    string, and its hash is what ``knowledge`` snapshots onto the generated set.
    Reformatting it here would break all three.
    """

    species_code: str
    scientific_name: str
    document_title: str
    document_body: str
    common_name: str | None = None

    def as_prompt_variables(self) -> dict[str, str]:
        """The values the Langfuse template is compiled with.

        Keys are exactly :data:`~mlops.knowledge.prompts.GENERATE_PROBES_VARIABLES`.
        """
        return {
            "species_code": self.species_code,
            "scientific_name": self.scientific_name,
            "common_name": self.common_name or self.scientific_name,
            "document_title": self.document_title,
            "document_body": self.document_body,
        }


@dataclass(frozen=True)
class GenerateProbesResult:
    """What comes back — a draft, before any human review.

    ``probe_set`` has already passed every check in
    :mod:`mlops.knowledge.schemas`; the rest is provenance, which ``knowledge``
    stores on its ``probe_set`` row so a bad batch can be traced to the prompt
    version that produced it.
    """

    probe_set: GeneratedProbeSet
    #: The model that produced it, as reported by the prompt config.
    model: str
    prompt_name: str
    prompt_version: int
    #: How many tries it took to pass validation. > 1 is worth noticing.
    attempts: int
    #: Langfuse trace id, so the caller can correlate its own row with the run —
    #: and so a human reviewer can be pointed at the trace they are judging.
    trace_id: str | None = None

    @property
    def prompt_ref(self) -> str:
        """``knowledge/generate-probes@7`` — what ``prompt_version`` columns hold."""
        return f"{self.prompt_name}@{self.prompt_version}"


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


def generate_probes(
    payload: GenerateProbesInput,
    *,
    label: str | None = PRODUCTION_LABEL,
    version: int | None = None,
    overrides: dict[str, Any] | None = None,
) -> GenerateProbesResult:
    """Generate a draft probe set from a research document.

    ``label`` / ``version`` / ``overrides`` exist so ``experiment.py`` can pin a
    prompt version and drive this exact function — experiments and production
    then share one code path.

    Raises:
        ProbeGenerationError: no attempt produced a valid set.
        LangfuseNotConfiguredError: the ``knowledge`` project has no key pair.
    """
    prompt = prompts.get(prompts.GENERATE_PROBES, label=label, version=version)
    config = GenerationConfig.from_prompt_config(prompt.config, overrides=overrides)
    template = ChatPromptTemplate.from_messages(prompt.get_langchain_prompt())
    # Structured output puts the JSON schema in the request itself, so the
    # model is constrained rather than merely instructed.
    model = _build_model(config).with_structured_output(GeneratedProbeSet)

    client = get_client(COMPONENT)
    # One trace per document, with the repair rounds nested inside it as
    # generations. `propagate_attributes(prompt=…)` is what ties those
    # generations to the prompt version, which is how the Langfuse UI can show
    # a version's real-world behaviour next to its dataset runs.
    with (
        client.start_as_current_observation(
            name="knowledge.generate_probes",
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
        model=config.model,
        prompt_name=prompt.name,
        prompt_version=prompt.version,
        attempts=attempts,
        trace_id=trace_id,
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
