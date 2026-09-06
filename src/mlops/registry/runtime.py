"""Execution code for ``registry`` — species identification.

Owner: TODO

Runs once per plant, when it is registered: a frame goes to the on-prem VLM and
comes back as a species. ``registry`` decides what to do with a low-confidence
answer — a wrong species silently poisons every probe that follows, so an
abstention is worth more here than a confident guess.

Inputs are plain values — ``mlops`` must not import a bounded context, so the
calling context flattens its own models onto :class:`IdentifySpeciesInput`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mlops.settings import PRODUCTION_LABEL


@dataclass(frozen=True)
class IdentifySpeciesInput:
    """What ``src/registry`` passes in.

    TODO: the frame, and the species codes ``knowledge`` covers so the model
    picks from a closed set instead of naming anything botanical.
    """


@dataclass(frozen=True)
class SpeciesGuess:
    """What comes back.

    TODO: the chosen species code (or none, when the model would not commit),
    its confidence, and the runners-up for a disambiguation prompt.
    """

    #: Langfuse trace id, so the caller can correlate its own row with the run.
    trace_id: str | None = None


def identify_species(
    payload: IdentifySpeciesInput,
    *,
    label: str | None = PRODUCTION_LABEL,
    version: int | None = None,
    overrides: dict[str, Any] | None = None,
) -> SpeciesGuess:
    """Identify the species in a frame.

    ``label`` / ``version`` / ``overrides`` exist so ``experiment.py`` can pin a
    prompt version and drive this exact function — experiments and production
    then share one code path. The request path passes none of them.
    """
    raise NotImplementedError
