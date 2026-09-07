"""The generate → validate → repair loop, and the config it reads off the prompt.

The model is a stub returning canned answers: what is under test is that an
invalid answer comes back to the model *as a correction* rather than as a
re-roll, and that a set which never validates is raised rather than returned.
"""

from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate

from mlops.knowledge import runtime
from mlops.knowledge.runtime import (
    GenerateProbesInput,
    GenerationConfig,
    ProbeGenerationError,
)

DOCUMENT = "The leaves droop noticeably when it dries out."

PAYLOAD = GenerateProbesInput(
    species_code="spath",
    scientific_name="Spathiphyllum wallisii",
    common_name="Peace lily",
    document_title="watering",
    document_body=DOCUMENT,
)

TEMPLATE = ChatPromptTemplate.from_messages(
    [("system", "You write probes."), ("human", "{document_title}: {document_body}")]
)


def valid_probe(**overrides: Any) -> dict[str, Any]:
    return {
        "slug": "water_deficit.leaf_droop",
        "care_need": "water_deficit",
        "priority": 1,
        "is_screening": True,
        "question": "Are the leaves drooping or limp?",
        "worse_looks_like": "limp, folded leaves",
        "better_looks_like": "firm, upright leaves",
        "not_this": "natural night-time leaf folding",
        "evidence_quote": "The leaves droop noticeably when it dries out",
        "actions": [
            {
                "instruction": "Water thoroughly until it drains.",
                "urgency": "today",
                "expect_typical_hours": 12,
                "expect_max_hours": 48,
            }
        ],
        **overrides,
    }


class ScriptedModel:
    """Returns the next scripted answer, recording what it was asked."""

    def __init__(self, *answers: dict[str, Any]) -> None:
        self._answers = list(answers)
        self.calls: list[list[Any]] = []

    def invoke(self, messages: list[Any], config: Any = None) -> dict[str, Any]:
        self.calls.append(list(messages))
        return self._answers[min(len(self.calls) - 1, len(self._answers) - 1)]


@pytest.fixture(autouse=True)
def no_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tracing is not what these tests are about, and it needs credentials."""
    monkeypatch.setattr(runtime, "get_callback_handler", lambda _: None)


def _run(model: ScriptedModel, *, max_attempts: int = 3) -> Any:
    return runtime._run_with_repair(
        TEMPLATE,
        model,  # type: ignore[arg-type]
        PAYLOAD,
        GenerationConfig(model="stub", max_attempts=max_attempts),
    )


def test_a_valid_first_answer_is_returned_as_is() -> None:
    model = ScriptedModel({"probes": [valid_probe()]})

    probe_set, attempts = _run(model)

    assert attempts == 1
    assert len(model.calls) == 1
    assert probe_set.probes[0].slug == "water_deficit.leaf_droop"


def test_an_invalid_answer_is_sent_back_as_a_correction() -> None:
    """The retry must carry the original task *and* what was wrong with the answer."""
    model = ScriptedModel(
        {"probes": [valid_probe(slug="not a slug")]},
        {"probes": [valid_probe()]},
    )

    probe_set, attempts = _run(model)

    assert attempts == 2
    first, second = model.calls
    # The second call replays the first conversation, plus the correction.
    assert second[: len(first)] == first
    repair = second[-1]
    assert isinstance(repair, HumanMessage)
    assert "slug" in str(repair.content)
    assert probe_set.probes[0].slug == "water_deficit.leaf_droop"


def test_an_ungrounded_quote_is_repaired_the_same_way() -> None:
    """A quote the document does not contain is a hallucination, not a typo."""
    model = ScriptedModel(
        {"probes": [valid_probe(evidence_quote="Mist the leaves twice a week.")]},
        {"probes": [valid_probe()]},
    )

    _, attempts = _run(model)

    assert attempts == 2
    assert "evidence_quote" in str(model.calls[1][-1].content)


def test_a_set_that_never_validates_is_raised_not_returned() -> None:
    """There is no 'mostly valid' way out of this module."""
    model = ScriptedModel({"probes": [valid_probe(slug="not a slug")]})

    with pytest.raises(ProbeGenerationError) as exc:
        _run(model, max_attempts=2)

    assert exc.value.attempts == 2
    assert len(model.calls) == 2
    assert "slug" in str(exc.value.last_error)


def test_each_repair_round_adds_exactly_one_message() -> None:
    """A loop that re-sent the whole history twice would blow up the context."""
    model = ScriptedModel({"probes": [valid_probe(slug="not a slug")]})

    with pytest.raises(ProbeGenerationError):
        _run(model, max_attempts=3)

    lengths = [len(call) for call in model.calls]
    assert lengths == [lengths[0], lengths[0] + 1, lengths[0] + 2]


# --------------------------------------------------------------------------- #
# hyper-parameters come off the prompt version, not out of this repository
# --------------------------------------------------------------------------- #


def test_the_prompt_config_supplies_the_model_and_its_parameters() -> None:
    config = GenerationConfig.from_prompt_config(
        {"model": "gpt-4o", "temperature": 0.3, "max_tokens": 4096, "top_p": 0.9}
    )

    assert (config.model, config.temperature, config.max_tokens) == (
        "gpt-4o",
        0.3,
        4096,
    )
    # Anything else is passed through to the client rather than dropped.
    assert config.extra == {"top_p": 0.9}


def test_an_experiment_can_override_one_parameter() -> None:
    config = GenerationConfig.from_prompt_config(
        {"model": "gpt-4o", "temperature": 0.3}, overrides={"temperature": 0.0}
    )

    assert config.temperature == 0.0


def test_everything_but_the_model_has_a_default() -> None:
    """A prompt authored with a bare `{"model": …}` must still run."""
    config = GenerationConfig.from_prompt_config({"model": "gpt-4o"})

    assert config.temperature == 0.0
    assert config.max_tokens is None
    assert config.max_attempts == runtime.DEFAULT_MAX_ATTEMPTS


@pytest.mark.parametrize("prompt_config", [None, {}, {"temperature": 0.3}])
def test_a_prompt_config_with_no_model_is_an_error(prompt_config: Any) -> None:
    """There is no environment fallback, on purpose.

    A default would mean the model a run used is not recoverable from the prompt
    version it names, and two runs of "v7" could differ by deployment — which
    makes comparing versions meaningless.
    """
    with pytest.raises(ValueError, match="no model in the Langfuse prompt config"):
        GenerationConfig.from_prompt_config(prompt_config)


def test_max_attempts_is_never_zero() -> None:
    """A config of 0 would return a ProbeGenerationError without ever asking."""
    assert GenerationConfig.from_prompt_config({"model": "m", "max_attempts": 0}) == (
        GenerationConfig(model="m", max_attempts=1)
    )
