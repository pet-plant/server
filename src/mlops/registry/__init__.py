"""MLOps for ``registry`` — species identification.

Owner: TODO · Langfuse project: ``registry``

What ``src/registry`` imports::

    from mlops.registry import IdentifySpeciesInput, identify_species

Self-contained: this package owns its own prompt handling, model calls, tracing,
experiments and scorers. Add modules as the work needs them.
"""

from mlops.registry.runtime import (
    IdentifySpeciesInput,
    SpeciesGuess,
    identify_species,
)

__all__ = ["IdentifySpeciesInput", "SpeciesGuess", "identify_species"]
