"""Prompts for the ``knowledge`` Langfuse project.

Owner: TODO

Keep the prompt names for this project here so ``runtime`` and ``experiment``
resolve them through one place. The prompt bodies and their hyper-parameters
live in Langfuse (a version's ``config``), never in this repository.
"""

from __future__ import annotations

from typing import Any, Final

from langfuse.model import ChatPromptClient

from mlops.client import get_client
from mlops.settings import PRODUCTION_LABEL, Component

COMPONENT: Final = Component.KNOWLEDGE

#: Research document → probes. A **chat** prompt whose variables are exactly
#: :data:`GENERATE_PROBES_VARIABLES`; its ``config`` supplies the model
#: hyper-parameters (see :class:`mlops.knowledge.runtime.GenerationConfig`).
GENERATE_PROBES: Final[str] = "knowledge/generate-probes"

#: The variables the ``GENERATE_PROBES`` template is compiled with. Authoring a
#: version in Langfuse that uses a name outside this set fails at compile time,
#: which is the point — this tuple is the contract between the prompt author and
#: :mod:`mlops.knowledge.runtime`.
GENERATE_PROBES_VARIABLES: Final[tuple[str, ...]] = (
    "species_code",
    "scientific_name",
    "common_name",
    "document_title",
    "document_body",
)

#: How long a fetched prompt is reused before Langfuse is asked again. Probe
#: generation is an offline authoring job, so a stale minute costs nothing and
#: the network round-trip per document does.
CACHE_TTL_SECONDS: Final[int] = 300


def get(
    name: str = GENERATE_PROBES,
    *,
    label: str | None = PRODUCTION_LABEL,
    version: int | None = None,
) -> ChatPromptClient:
    """Fetch a chat prompt version from this component's Langfuse project.

    Pass ``label`` in the request path (always :data:`PRODUCTION_LABEL`) or
    ``version`` from an experiment, so a dataset run is reproducible. Passing
    both is a mistake — a pinned version and a moving label disagree the moment
    the label is promoted.
    """
    if version is not None and label is not None and label != PRODUCTION_LABEL:
        raise ValueError("pass either `label` or `version`, not both")
    kwargs: dict[str, Any] = {"type": "chat", "cache_ttl_seconds": CACHE_TTL_SECONDS}
    if version is not None:
        kwargs["version"] = version
    else:
        kwargs["label"] = label
    prompt = get_client(COMPONENT).get_prompt(name, **kwargs)
    # `type="chat"` is what we ask for, not what we are guaranteed: a text
    # prompt authored under this name comes back as a TextPromptClient and would
    # fail further downstream, in message compilation.
    if not isinstance(prompt, ChatPromptClient):  # pragma: no cover - defensive
        raise TypeError(
            f"Langfuse prompt {name!r} is a text prompt; it must be a chat prompt"
        )
    return prompt
