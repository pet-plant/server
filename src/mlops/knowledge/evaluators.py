"""Automatic checks for ``knowledge`` experiments — well-formedness only.

Owner: TODO

**These do not measure whether the probes are good.** Whether a probe is
botanically right is a human judgement and lives in :mod:`mlops.knowledge.review`.
What is left over is still worth measuring, because it is exactly what a prompt
regression looks like before a person ever sees it:

| Score | Says |
|---|---|
| ``validation_passed`` | the set satisfied the schema at all |
| ``repair_attempts`` | how many rounds it took (1 = first try) |
| ``probe_count`` | how many probes came out of one document |
| ``care_need_coverage`` | how many distinct care needs they span |

A prompt version that needs three repair rounds on half the dataset is worse
than one that needs none, and that is visible here without anyone reading a
probe. It just is not the same question as "are these the right probes".

Every function is an evaluator in the Langfuse sense: keyword-only ``input`` /
``output`` / ``expected_output`` / ``metadata``, returning
:class:`langfuse.Evaluation`. ``output`` is the
:class:`~mlops.knowledge.contract.GenerateProbesResult` the task function
returned, or ``None`` when generation failed outright.
"""

from __future__ import annotations

from typing import Any

from langfuse import Evaluation

from mlops.knowledge.contract import GenerateProbesResult


def _result(output: Any) -> GenerateProbesResult | None:
    return output if isinstance(output, GenerateProbesResult) else None


def validation_passed(*, output: Any = None, **_: Any) -> Evaluation:
    """1 when a set survived validation, 0 when every attempt was rejected.

    The floor under everything else: a prompt version that scores below 1 here
    is not a candidate, whatever a human thinks of the sets it did produce.
    """
    passed = _result(output) is not None
    return Evaluation(
        name="validation_passed",
        value=1.0 if passed else 0.0,
        comment=None if passed else "no attempt produced a valid probe set",
    )


def repair_attempts(*, output: Any = None, **_: Any) -> Evaluation:
    """How many model calls it took to pass validation. Lower is better; 1 is ideal."""
    result = _result(output)
    return Evaluation(
        name="repair_attempts",
        value=float(result.attempts) if result else 0.0,
        comment=None if result else "not reached",
    )


def probe_count(*, output: Any = None, **_: Any) -> Evaluation:
    """How many probes one research document yielded.

    Not a quality signal on its own — read it against the document. A sudden
    drop across a dataset usually means the prompt started summarising.
    """
    result = _result(output)
    return Evaluation(
        name="probe_count",
        value=float(len(result.probe_set.probes)) if result else 0.0,
    )


def care_need_coverage(*, output: Any = None, **_: Any) -> Evaluation:
    """Distinct ``care_need`` values in the set.

    Catches the common failure where every probe is a variation on one problem
    (five ways of looking at underwatering) and the rest of the document is
    ignored.
    """
    result = _result(output)
    if result is None:
        return Evaluation(name="care_need_coverage", value=0.0, comment="not reached")
    needs = {probe.care_need for probe in result.probe_set.probes}
    return Evaluation(
        name="care_need_coverage",
        value=float(len(needs)),
        comment=", ".join(sorted(needs)),
    )


#: Applied to every item of a dataset run. Quality is not in here — see
#: :mod:`mlops.knowledge.review` for the half a person has to do.
EVALUATORS: list[Any] = [
    validation_passed,
    repair_attempts,
    probe_count,
    care_need_coverage,
]
