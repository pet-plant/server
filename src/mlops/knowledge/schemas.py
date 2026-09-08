"""The output contract for probe generation — and the validation of it.

Owner: TODO

These models are **the schema handed to the LLM** (as a JSON schema, via
``with_structured_output``) *and* the gate every generated set must pass before
``knowledge`` is allowed to see it. Both roles matter: the first makes
well-formed output likely, the second makes it certain.

Deliberately Pydantic and nothing else — ``mlops`` must not import a bounded
context, so these are plain models that mirror the *shape* ``knowledge`` stores
without depending on its ORM. The calling context maps them onto its own rows.

Three layers of checking, weakest to strongest:

1. **JSON schema** — the model is constrained to the field names and types.
2. **Field / model validators here** — the domain rules the JSON schema cannot
   express: slug format, slug ↔ ``care_need`` agreement, unique slugs, the
   ``expect_typical_hours <= expect_max_hours`` ordering.
3. :func:`GeneratedProbeSet.validate_against_document` — grounding. Every
   ``evidence_quote`` must actually occur in the research document. This is the
   anti-hallucination check, and it needs the source text, so it cannot live in
   a validator.

Anything the model gets wrong here comes back as a ``ValidationError`` that
:mod:`mlops.knowledge.runtime` feeds to it as a repair instruction.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: How soon an action has to happen. Mirrors ``probe_action.urgency``.
Urgency = Literal["today", "this_week", "this_month"]

#: ``water_deficit.leaf_droop`` — ``<care_need>.<observation>``.
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

#: An identifier segment: ``water_deficit``, ``light_excess``, ….
NAME_PATTERN = r"^[a-z][a-z0-9_]*$"

#: A month, in hours. An action whose effect takes longer than this is not
#: something a daily-cadence assessment loop can verify.
MAX_EXPECT_HOURS = 720

_WHITESPACE = re.compile(r"\s+")


def _normalise(text: str) -> str:
    """Fold the differences that carry no meaning, for quote matching.

    Whitespace, because the model re-wraps what it quotes. Case, because a span
    lifted from the middle of a sentence comes back capitalised as if it were
    the start of one — the words are right and only the typography moved, which
    is not what this check is about.
    """
    return _WHITESPACE.sub(" ", text).strip().casefold()


class GeneratedAction(BaseModel):
    """One thing the plant's owner should do when this probe fires.

    The two hour fields are a re-check window, not a botanical estimate: they
    decide when the system looks again and when it is allowed to raise the same
    alert a second time.
    """

    model_config = ConfigDict(extra="forbid")

    instruction: Annotated[
        str,
        Field(
            min_length=4,
            max_length=400,
            description=(
                "What the plant's owner should physically do, in one or two "
                "sentences addressed to them."
            ),
        ),
    ]
    urgency: Annotated[
        Urgency,
        Field(description="How soon the owner should act."),
    ]
    expect_typical_hours: Annotated[
        int,
        Field(
            ge=1,
            le=MAX_EXPECT_HOURS,
            description=(
                "Hours until the first visible sign of improvement would "
                "normally appear, if the owner does this now. The SMALLER of "
                "the two hour fields."
            ),
        ),
    ]
    expect_max_hours: Annotated[
        int,
        Field(
            ge=1,
            le=MAX_EXPECT_HOURS,
            description=(
                "Grace period in hours: the same alert is not raised again "
                "until this has elapsed. Must be GREATER THAN OR EQUAL TO "
                "expect_typical_hours — it is the outer edge of the same "
                "window, so it is never the smaller number. When recovery is "
                "slower than the 720-hour ceiling, use 720 for both rather "
                "than inverting them."
            ),
        ),
    ]
    expected_signal: Annotated[
        str | None,
        Field(
            pattern=NAME_PATTERN,
            description=(
                "The visible sign of recovery to watch for, as a snake_case "
                "tag with underscores between words: 'leaf_recovery', "
                "'new_growth_appears'. Null when there is no single sign."
            ),
        ),
    ] = None

    @model_validator(mode="after")
    def _hours_are_ordered(self) -> GeneratedAction:
        if self.expect_max_hours < self.expect_typical_hours:
            raise ValueError(
                "expect_max_hours is the outer edge of the same window as "
                "expect_typical_hours, so it cannot be the smaller of the two: "
                f"got expect_max_hours={self.expect_max_hours} and "
                f"expect_typical_hours={self.expect_typical_hours}. Either raise "
                "expect_max_hours to at least expect_typical_hours, or lower "
                "expect_typical_hours if that was the number meant to be large."
            )
        return self


class GeneratedProbe(BaseModel):
    """One single-question visual check, answerable from one whole-plant photo.

    A vision model that has never seen this plant before gets one ordinary
    photograph of it and this probe. Everything here has to work under those
    conditions: no close-up, no crop, no memory of an earlier photo, no touch or
    smell, nothing about soil the camera cannot see.
    """

    model_config = ConfigDict(extra="forbid")

    slug: Annotated[
        str,
        Field(
            description=(
                "Identifier '<care_need>.<what is visible>' in snake_case, e.g. "
                "'water_deficit.leaf_droop'. The part before the dot must be "
                "exactly the care_need below. Unique within the set."
            ),
        ),
    ]
    care_need: Annotated[
        str,
        Field(
            pattern=NAME_PATTERN,
            description=(
                "The underlying condition, snake_case: 'water_deficit', "
                "'water_excess', 'light_excess', 'light_deficit', "
                "'cold_draught'. Use the same name for the same condition "
                "across probes."
            ),
        ),
    ]
    priority: Annotated[
        int,
        Field(
            ge=1,
            description="Order to check, 1 first. Each value used once in a set.",
        ),
    ]
    is_screening: Annotated[
        bool,
        Field(
            description=(
                "True for a cheap, broad check run first to decide whether the "
                "rest are worth running. At least one probe in the set must be "
                "true."
            ),
        ),
    ]
    question: Annotated[
        str,
        Field(
            min_length=8,
            max_length=300,
            description=(
                "One closed question about what is visible in the photo right "
                "now. Not two questions joined by 'and', and never a comparison "
                "with an earlier photo."
            ),
        ),
    ]
    worse_looks_like: Annotated[
        str,
        Field(
            min_length=4,
            max_length=300,
            description="What the photo shows when the problem is present.",
        ),
    ]
    better_looks_like: Annotated[
        str,
        Field(
            min_length=4,
            max_length=300,
            description="What the photo shows when the plant is fine.",
        ),
    ]
    not_this: Annotated[
        str,
        Field(
            min_length=4,
            max_length=300,
            description=(
                "The over-detection guard: the innocent look-alike that would "
                "otherwise be mistaken for this problem — normal ageing, a "
                "cosmetic blemish, the plant's own harmless behaviour. The "
                "research document usually names it."
            ),
        ),
    ]
    evidence_quote: Annotated[
        str,
        Field(
            min_length=8,
            max_length=1000,
            description=(
                "A span copied VERBATIM from the research document, word for "
                "word, that supports this probe. It is checked against the "
                "document; anything paraphrased or invented is rejected."
            ),
        ),
    ]

    actions: Annotated[
        list[GeneratedAction],
        Field(
            min_length=1,
            max_length=5,
            description="What to do when this probe fires. At least one.",
        ),
    ]

    @field_validator("slug")
    @classmethod
    def _slug_is_well_formed(cls, value: str) -> str:
        if not SLUG_PATTERN.match(value):
            raise ValueError(
                f"slug must be '<care_need>.<observation>' in snake_case, got {value!r}"
            )
        return value

    @model_validator(mode="after")
    def _slug_matches_care_need(self) -> GeneratedProbe:
        prefix = self.slug.split(".", 1)[0]
        if prefix != self.care_need:
            raise ValueError(
                f"slug prefix {prefix!r} must equal care_need {self.care_need!r}"
            )
        return self


class GeneratedProbeSet(BaseModel):
    """Every probe derived from one research document.

    Cover the distinct problems the document describes rather than several
    variations on one. If it only supports two probes, return two. Slugs and
    priorities are each unique across the set, and at least one probe must have
    is_screening set.
    """

    model_config = ConfigDict(extra="forbid")

    probes: Annotated[
        list[GeneratedProbe],
        Field(
            min_length=1,
            max_length=12,
            description=(
                "One per distinct problem the research document supports, "
                "ordered by the priority field."
            ),
        ),
    ]

    @model_validator(mode="after")
    def _identifiers_are_unique(self) -> GeneratedProbeSet:
        slugs = [p.slug for p in self.probes]
        if len(set(slugs)) != len(slugs):
            duplicates = sorted({s for s in slugs if slugs.count(s) > 1})
            raise ValueError(f"duplicate probe slugs: {', '.join(duplicates)}")
        priorities = [p.priority for p in self.probes]
        if len(set(priorities)) != len(priorities):
            raise ValueError(f"probe priorities must be unique, got {priorities}")
        return self

    @model_validator(mode="after")
    def _has_a_screening_probe(self) -> GeneratedProbeSet:
        if not any(p.is_screening for p in self.probes):
            raise ValueError(
                "at least one probe must have is_screening=true — assessment runs "
                "the screening probes first to decide whether to run the rest"
            )
        return self

    def validate_against_document(self, body: str) -> None:
        """Check every ``evidence_quote`` really occurs in ``body``.

        Whitespace and case are normalised on both sides (see :func:`_normalise`),
        but the wording itself has to match: a quote the document does not
        contain means the probe was invented rather than derived. The quote is
        kept exactly as the model wrote it — only the comparison is relaxed.

        Raises:
            UngroundedProbeError: naming the probes that failed.
        """
        haystack = _normalise(body)
        ungrounded = [
            probe.slug
            for probe in self.probes
            if _normalise(probe.evidence_quote) not in haystack
        ]
        if ungrounded:
            raise UngroundedProbeError(ungrounded)


class UngroundedProbeError(ValueError):
    """Raised when an ``evidence_quote`` does not occur in the research document."""

    def __init__(self, slugs: list[str]) -> None:
        self.slugs = slugs
        super().__init__(
            "evidence_quote not found verbatim in the research document for: "
            + ", ".join(slugs)
        )
