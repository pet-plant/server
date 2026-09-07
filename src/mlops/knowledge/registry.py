"""Which agent versions exist, and which one a caller gets.

Owner: TODO

Choosing a version is a **code change in the caller**, not configuration. That is
deliberate: swapping the agent structure changes what the system does, so it
should arrive through review and deployment like any other behaviour change. The
fast lever — swapping a prompt — is the Langfuse ``production`` label, and needs
neither.

Adding a version:

1. Copy ``agents/v1/`` to ``agents/v2/`` and change ``VERSION``.
2. Edit its prompts and its structure. Its Langfuse prompt names carry ``v2``,
   so it cannot disturb what v1 runs on.
3. Register it below.
4. Run its experiment, review the results, promote its prompts.
5. Point the caller at it — a one-line change, revertible the same way.

Old versions are kept, not deleted: a rollback is then a code revert rather than
an archaeology exercise.
"""

from __future__ import annotations

from typing import Final

from mlops.knowledge.agents.v1 import AGENT as _V1
from mlops.knowledge.contract import ProbeAgent

#: Every version that still exists. Keys are what ``probe_set.agent_version``
#: holds, so removing one orphans the rows that name it.
AGENTS: Final[dict[str, ProbeAgent]] = {_V1.version: _V1}

#: What `knowledge` uses today. Changing this is the deployment of a new agent
#: structure — one line, reviewed, revertible.
DEFAULT_VERSION: Final[str] = _V1.version


def get_agent(version: str | None = None) -> ProbeAgent:
    """The agent for ``version``, or :data:`DEFAULT_VERSION` when unset.

    Raises:
        KeyError: no such version — naming what does exist, because the usual
            cause is a rollback to a version that was deleted rather than kept.
    """
    try:
        return AGENTS[version or DEFAULT_VERSION]
    except KeyError:
        raise KeyError(
            f"no probe agent {version!r}; available: {sorted(AGENTS)}"
        ) from None
