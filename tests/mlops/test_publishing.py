"""Publishing prompt files: the repository is the source of truth.

The property that matters is idempotency. Every experiment run publishes, so if
an unchanged prompt still created a version, the version numbers would count
invocations instead of decisions and the history would stop being a record of
anything.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from mlops.knowledge import publishing
from mlops.knowledge.agents.v1 import AGENT


class FakeAgent:
    version = "vtest"

    def __init__(self, package_dir: Path) -> None:
        self.package_dir = package_dir

    def run(self, *_: Any, **__: Any) -> Any:  # pragma: no cover - never called
        raise NotImplementedError


@pytest.fixture
def agent(tmp_path: Path) -> FakeAgent:
    prompt = tmp_path / "prompts" / "generate-probes"
    prompt.mkdir(parents=True)
    (prompt / "system.md").write_text("You write probes.\n")
    (prompt / "user.md").write_text(
        "{{species_code}} {{scientific_name}} {{common_name}} "
        "{{document_title}} {{document_body}}\n"
    )
    (prompt / "config.json").write_text(json.dumps({"model": "gpt-4o"}))
    return FakeAgent(tmp_path)


def test_the_filesystem_is_the_list_of_prompts(agent: FakeAgent) -> None:
    """No second list to drift: the directory names are the prompt names."""
    sources = publishing.load_sources(agent)

    assert [s.name for s in sources] == ["knowledge/vtest/generate-probes"]
    assert [m["role"] for m in sources[0].messages] == ["system", "user"]
    assert sources[0].config == {"model": "gpt-4o"}


def test_a_message_file_must_be_named_after_its_role(agent: FakeAgent) -> None:
    (agent.package_dir / "prompts" / "generate-probes" / "notes.md").write_text("x")

    with pytest.raises(ValueError, match="role"):
        publishing.load_sources(agent)


def test_an_input_that_reaches_no_prompt_is_an_error(agent: FakeAgent) -> None:
    """A renamed variable would otherwise look like a bad prompt, not a wiring bug."""
    user = agent.package_dir / "prompts" / "generate-probes" / "user.md"
    user.write_text("{{species_code}}\n")

    with pytest.raises(ValueError, match="document_body"):
        publishing.check_variables(publishing.load_sources(agent))


def test_the_real_v1_prompts_load_and_cover_every_input() -> None:
    """The shipped agent must satisfy the same checks the bench applies."""
    sources = publishing.load_sources(AGENT)

    assert [s.name for s in sources] == ["knowledge/v1/generate-probes"]
    publishing.check_variables(sources)
    assert sources[0].config["model"]


def test_trailing_newlines_do_not_count_as_a_change(agent: FakeAgent) -> None:
    """An editor adding a final newline must not publish a new prompt version."""
    system = agent.package_dir / "prompts" / "generate-probes" / "system.md"
    before = publishing.load_sources(agent)[0].messages
    system.write_text(system.read_text() + "\n\n")

    assert publishing.load_sources(agent)[0].messages == before
