"""Published in-process interface for other bounded contexts.

``assessment`` needs the probe definitions and ``advice`` needs the actions;
both call :func:`get_species_metrics` instead of reaching into the ``knowledge``
schema. The return value is a Pydantic model that serialises straight to JSON
(``bundle.model_dump(mode="json")``).
"""

from sqlalchemy.orm import Session

from knowledge.schemas import MetricRead, SpeciesMetricsBundle
from knowledge.service import get_current_metric_set, is_metric_set_stale


def get_species_metrics(
    session: Session, species_code: str
) -> SpeciesMetricsBundle | None:
    """Current approved metrics + actions for ``species_code``.

    Returns ``None`` when the species has no approved metric set yet.
    """
    metric_set = get_current_metric_set(session, species_code)
    if metric_set is None:
        return None
    return SpeciesMetricsBundle(
        species_code=species_code,
        metric_set_id=metric_set.id,
        status=metric_set.status,
        is_stale=is_metric_set_stale(session, metric_set.id),
        generated_at=metric_set.generated_at,
        metrics=[MetricRead.model_validate(m) for m in metric_set.metrics],
    )
