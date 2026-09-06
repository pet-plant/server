"""One Langfuse client per component project.

Credential plumbing only — it hands a component owner a client pointed at the
right project and stops there. How prompts, traces and datasets are used through
it is each component package's own business.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from mlops.settings import Component, credentials_for

if TYPE_CHECKING:
    from langfuse import Langfuse


@lru_cache(maxsize=len(Component))
def get_client(component: Component) -> Langfuse:
    """The Langfuse client for ``component``'s project.

    Cached per component: each carries its own credentials and its own
    background flush thread. Raises when that component's key pair is missing —
    a component whose project is unconfigured must never fall through to
    another's.
    """
    _ = credentials_for(component)
    raise NotImplementedError


def is_configured(component: Component) -> bool:
    """Whether ``component`` has a usable Langfuse key pair."""
    return credentials_for(component).is_configured


def flush(component: Component) -> None:
    """Flush pending events for one component (call before process exit)."""
    raise NotImplementedError
