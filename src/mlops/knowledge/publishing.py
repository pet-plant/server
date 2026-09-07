"""Push an agent version's prompt files to Langfuse.

Owner: TODO

**The repository is the source of truth for prompt text.** Prompts are edited
here, in ``agents/<version>/prompts/``, and published from here — not written in
the Langfuse UI. That way a prompt change is a diff someone reviews, the history
lives with the code that depends on it, and a Langfuse project can be rebuilt
from scratch.

What Langfuse owns instead is everything the repository cannot: the version
registry, the traces and dataset runs each version produced, the human scores on
them, and the ``production`` label that decides which version is live. Promotion
stays a label move in the Langfuse UI — no deployment, and no code change.

## Layout

```
agents/v1/prompts/generate-probes/
├── system.md      ─┐ chat messages, ordered by filename; the role is the
├── user.md        ─┘ filename stem (a leading `01-` is allowed and ignored)
└── config.json       model, temperature, … — the prompt version's `config`
```

The directory name becomes the Langfuse prompt name
``knowledge/<agent version>/<directory>``. There is no second list of prompts to
keep in sync — the filesystem is the list.

## Publishing is idempotent

:func:`sync` compares each prompt against the current ``latest`` version and only
creates a new one when the text or config actually changed. Without that, every
experiment run would inflate the version numbers and the history would be noise
instead of a record of decisions.

Nothing published here is labelled ``production``. A new version arrives live
only when a person moves that label, after reading the experiment results.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langfuse.api.commons.errors.not_found_error import NotFoundError

from mlops.client import get_client
from mlops.knowledge.contract import PROMPT_VARIABLES, PromptRef
from mlops.settings import Component

if TYPE_CHECKING:
    from mlops.knowledge.contract import ProbeAgent

COMPONENT = Component.KNOWLEDGE

#: Roles a message file may carry. Anything else is a typo, not a new feature.
ROLES = ("system", "user", "assistant")

_ORDER_PREFIX = re.compile(r"^\d+[-_]")


@dataclass(frozen=True)
class PromptSource:
    """One prompt as it exists on disk."""

    #: Full Langfuse name, ``knowledge/v1/generate-probes``.
    name: str
    messages: list[dict[str, str]]
    config: dict[str, Any]

    def uses(self, variable: str) -> bool:
        return any(f"{{{{{variable}}}}}" in m["content"] for m in self.messages)


def _role_of(path: Path) -> str:
    role = _ORDER_PREFIX.sub("", path.stem)
    if role not in ROLES:
        raise ValueError(
            f"{path}: message file must be named after its role {ROLES} "
            "(optionally prefixed '01-')"
        )
    return role


def load_sources(agent: ProbeAgent) -> list[PromptSource]:
    """Read every prompt this agent version keeps on disk.

    Ordered by filename, so ``system.md`` precedes ``user.md`` without anything
    having to say so.
    """
    root = agent.package_dir / "prompts"
    if not root.is_dir():
        raise FileNotFoundError(f"{root} does not exist")

    sources = []
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        files = sorted(directory.glob("*.md"))
        if not files:
            raise FileNotFoundError(f"{directory} has no message files")
        # Trailing newlines are an artefact of the editor, not of the prompt.
        # Stripping both here and on the comparison keeps a pure whitespace
        # change from looking like a new version.
        messages = [
            {"role": _role_of(f), "content": f.read_text("utf-8").rstrip("\n")}
            for f in files
        ]
        config_file = directory / "config.json"
        config = json.loads(config_file.read_text("utf-8")) if config_file.is_file() else {}
        sources.append(
            PromptSource(
                name=f"knowledge/{agent.version}/{directory.name}",
                messages=messages,
                config=config,
            )
        )
    return sources


def check_variables(sources: list[PromptSource]) -> None:
    """Every input variable must reach the model through some prompt.

    A renamed variable otherwise shows up as a document the model never saw,
    which reads as a bad prompt rather than as the wiring mistake it is.
    """
    unused = [
        name
        for name in PROMPT_VARIABLES
        if not any(source.uses(name) for source in sources)
    ]
    if unused:
        raise ValueError(
            f"no prompt uses {unused}; those inputs would never reach the model"
        )


def _as_message(raw: Any) -> dict[str, str] | None:
    """One stored message, or ``None`` for anything that is not a plain message.

    Langfuse chat prompts may also hold placeholders. None of ours do; if one
    ever appears it is dropped here, which makes the comparison say "changed"
    and republish every run — loud enough to notice, unlike silently matching.
    """
    if isinstance(raw, dict) and "role" in raw and "content" in raw:
        return {"role": str(raw["role"]), "content": str(raw["content"]).rstrip("\n")}
    return None


def _current(name: str) -> tuple[int, list[dict[str, str]], dict[str, Any]] | None:
    """The newest version of ``name`` in Langfuse, or ``None`` if it has none."""
    try:
        prompt = get_client(COMPONENT).get_prompt(
            name, label="latest", type="chat", cache_ttl_seconds=0, max_retries=1
        )
    except NotFoundError:
        # A prompt nobody has published yet. Every other failure — auth, a bad
        # host, the service being down — must still surface, or `sync` would
        # quietly publish a duplicate v1 over a prompt that already exists.
        return None
    messages = [m for m in map(_as_message, prompt.prompt) if m is not None]
    config = prompt.config if isinstance(prompt.config, dict) else {}
    return prompt.version, messages, config


def sync(agent: ProbeAgent, *, commit_message: str | None = None) -> dict[str, int]:
    """Publish this agent's prompts and return the versions to run against.

    The returned mapping is what an experiment passes as ``pins``: the exact
    versions on disk right now, whether they were just created or already
    matched what Langfuse held. Pinning by number rather than by a moving label
    is what makes a dataset run reproducible after the fact.

    New versions are created **unlabelled** — publishing never deploys.
    """
    sources = load_sources(agent)
    check_variables(sources)
    client = get_client(COMPONENT)

    pins: dict[str, int] = {}
    for source in sources:
        current = _current(source.name)
        if current is not None and current[1:] == (source.messages, source.config):
            pins[source.name] = current[0]
            continue
        created = client.create_prompt(  # type: ignore[call-overload]
            name=source.name,
            type="chat",
            prompt=source.messages,
            config=source.config,
            labels=[],  # never deploy on publish; a person moves `production`
            commit_message=commit_message,
        )
        pins[source.name] = created.version
    client.flush()
    return pins


def describe(pins: dict[str, int]) -> str:
    """``knowledge/v1/generate-probes@4`` lines, for a run's log and metadata."""
    return ", ".join(str(PromptRef(name, version)) for name, version in pins.items())
