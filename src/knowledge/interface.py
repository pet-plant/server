"""Published in-process interface for other bounded contexts.

``assessment`` needs the probe definitions and ``advice`` needs the actions;
both call :func:`get_species_probes` instead of reaching into the ``knowledge``
schema. ``registry`` calls :func:`get_species` to check a plant's species code.
Return values are Pydantic models that serialise straight to JSON
(``bundle.model_dump(mode="json")``).
"""

from sqlalchemy.orm import Session

from knowledge.models import Species
from knowledge.schemas import ProbeRead, SpeciesProbesBundle, SpeciesRead
from knowledge.service import get_approved_probe_set, is_probe_set_stale


def get_species_probes(
    session: Session, species_code: str
) -> SpeciesProbesBundle | None:
    """The approved probes + actions for ``species_code``.

    Returns ``None`` when the species has no approved probe set yet. At most one
    set per species is ever approved, so there is nothing to choose between.
    """
    probe_set = get_approved_probe_set(session, species_code)
    if probe_set is None:
        return None
    return SpeciesProbesBundle(
        species_code=species_code,
        probe_set_id=probe_set.id,
        status=probe_set.status,
        is_stale=is_probe_set_stale(session, probe_set.id),
        generated_at=probe_set.generated_at,
        probes=[ProbeRead.model_validate(p) for p in probe_set.probes],
    )


def get_species(session: Session, species_code: str) -> SpeciesRead | None:
    """The catalogue entry for ``species_code``, or ``None`` if it is unknown."""
    species = session.get(Species, species_code)
    return None if species is None else SpeciesRead.model_validate(species)
