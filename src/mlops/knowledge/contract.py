"""The interface between ``knowledge`` and whichever agent generates its probes.

Owner: TODO

Everything in this module is what a caller may depend on. The agent behind it —
one shot with a repair loop, a plan/draft/critique graph, something else — is
swappable without any of these shapes changing, which is the point: ``knowledge``
maps :class:`GenerateProbesResult` onto rows and does not care how it was made.

**This interface is not frozen yet, and the docs must not claim it is.** The
probe schema is still moving (``crop`` was removed from it recently), and a
change there breaks every agent version at once. Freezing is a promise worth
making only once two or three versions have shipped and the shape has stopped
arguing with the domain. Until then, treat a change here as a change to *all*
agents and update them together.

## Versioning

One agent version = one package under ``agents/`` = its own namespace of Langfuse
prompts (``knowledge/<version>/<prompt>``). Because the prompt names differ, each
version has its **own** ``production`` label: promoting v2's prompt cannot move
what v1 runs on.

Which version production uses is a code change in the caller — see
:mod:`mlops.knowledge.registry`. Which *prompt version* it uses is a label move
in Langfuse, no deployment. Two levers, deliberately at different speeds.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from mlops.knowledge.schemas import GeneratedProbeSet


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
class PromptRef:
    """Exactly which prompt version a run resolved.

    An agent may use several prompts, so "which version was this?" needs one of
    these per prompt. Recorded on every result: a run launched by label is still
    reproducible afterwards because the labels it *resolved to* are kept.
    """

    name: str
    version: int

    def __str__(self) -> str:
        return f"{self.name}@{self.version}"


@dataclass(frozen=True)
class GenerateProbesInput:
    """What ``src/knowledge`` passes in.

    ``document_body`` is the research text **verbatim** — the model quotes it
    back as ``evidence_quote``, the grounding check matches against this exact
    string, and its hash is what ``knowledge`` snapshots onto the generated set.
    Reformatting it here would break all three.

    Text only, and it must stay that way: no plant imagery is ever sent to the
    external LLM, which is a property of this call site. There is no image field
    here and none should be added.
    """

    species_code: str
    scientific_name: str
    document_title: str
    document_body: str
    common_name: str | None = None

    def as_prompt_variables(self) -> dict[str, str]:
        """The values a prompt template is compiled with.

        Every agent version's prompts are written against these names, so this
        is the contract between the prompt author and the agent.
        """
        return {
            "species_code": self.species_code,
            "scientific_name": self.scientific_name,
            "common_name": self.common_name or self.scientific_name,
            "document_title": self.document_title,
            "document_body": self.document_body,
        }


#: The variable names :meth:`GenerateProbesInput.as_prompt_variables` supplies.
#: A prompt using anything outside this set fails to compile, which is the point.
PROMPT_VARIABLES: tuple[str, ...] = (
    "species_code",
    "scientific_name",
    "common_name",
    "document_title",
    "document_body",
)


@dataclass(frozen=True)
class GenerateProbesResult:
    """What comes back — a draft, before any human review.

    ``probe_set`` has already passed every check in
    :mod:`mlops.knowledge.schemas`; the rest is provenance, which ``knowledge``
    stores on its ``probe_set`` row so a bad batch can be traced back to the
    agent version and prompt versions that produced it.
    """

    probe_set: GeneratedProbeSet
    #: Which agent produced it — ``"v1"``. Stored, so a regression can be
    #: attributed to a structure change rather than a prompt change.
    agent_version: str
    #: The model, as named by the prompt config the run resolved.
    model: str
    #: Every prompt version the run actually used.
    prompts: tuple[PromptRef, ...]
    #: How many model calls it took to pass validation. > 1 is worth noticing.
    attempts: int
    #: Langfuse trace id, so the caller can correlate its own row with the run —
    #: and so a human reviewer can be pointed at the trace they are judging.
    trace_id: str | None = None

    @property
    def prompt_ref(self) -> str:
        """``knowledge/v1/generate-probes@7`` — what a provenance column holds."""
        return ", ".join(str(p) for p in self.prompts)


@runtime_checkable
class ProbeAgent(Protocol):
    """One way of turning a research document into a validated probe set.

    An implementation lives in ``agents/<version>/agent.py`` and keeps its prompt
    files in ``agents/<version>/prompts/<prompt-name>/``. Nothing outside its own
    package may be imported by another version: two versions coexist precisely so
    that changing one cannot disturb the other.
    """

    #: Directory name under ``agents/``, and the middle segment of its Langfuse
    #: prompt names. ``"v1"``.
    version: str

    #: The package directory, so publishing can find ``prompts/`` without a
    #: second list to keep in sync with the filesystem.
    package_dir: Path

    def run(
        self,
        payload: GenerateProbesInput,
        *,
        label: str | None = ...,
        pins: Mapping[str, int] | None = ...,
        overrides: dict[str, Any] | None = ...,
    ) -> GenerateProbesResult:
        """Generate one validated probe set, or raise.

        ``label`` resolves each prompt in production (normally ``production``).
        ``pins`` overrides that with exact versions, keyed by Langfuse prompt
        name — how an experiment runs a candidate it has just published.
        ``overrides`` patches the hyper-parameters from the prompt config.

        **Experiments call this same method.** A separate experiment-only path
        would stop the bench predicting production, which is the only reason to
        run a bench at all.

        Raises:
            ProbeGenerationError: no attempt produced a valid set.
        """
        ...
