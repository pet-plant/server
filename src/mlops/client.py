"""One Langfuse client per component project.

Credential plumbing only — it hands a component owner a client pointed at the
right project and stops there. How prompts, traces and datasets are used through
it is each component package's own business.

The Langfuse SDK keeps its own registry keyed by public key, which is what makes
several projects in one process work: constructing a client registers it, and
``CallbackHandler(public_key=…)`` then resolves back to that same client. Never
build a handler without a public key here — it would fall through to whichever
project happened to be constructed first.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from mlops.settings import Component, credentials_for

if TYPE_CHECKING:
    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler


class LangfuseNotConfiguredError(RuntimeError):
    """Raised when a component's Langfuse key pair is missing from the settings."""

    def __init__(self, component: Component) -> None:
        self.component = component
        super().__init__(
            f"No Langfuse credentials for the {component.value!r} project — set "
            f"LANGFUSE_HOST, LANGFUSE_{component.value.upper()}_PUBLIC_KEY and "
            f"LANGFUSE_{component.value.upper()}_SECRET_KEY."
        )


@lru_cache(maxsize=len(Component))
def get_client(component: Component) -> Langfuse:
    """The Langfuse client for ``component``'s project.

    Cached per component: each carries its own credentials and its own
    background flush thread. Raises when that component's key pair is missing —
    a component whose project is unconfigured must never fall through to
    another's.
    """
    from langfuse import Langfuse

    credentials = credentials_for(component)
    if not credentials.is_configured:
        raise LangfuseNotConfiguredError(component)
    return Langfuse(
        public_key=credentials.public_key,
        secret_key=credentials.secret_key,
        host=credentials.host,
    )


def get_callback_handler(component: Component) -> CallbackHandler:
    """A LangChain callback handler bound to ``component``'s Langfuse project.

    Pass it in the ``callbacks`` of a chain invocation and the whole chain —
    prompt, model call, token usage, latency — is traced without any manual
    span bookkeeping.
    """
    from langfuse.langchain import CallbackHandler

    # Constructing the client first is what registers this public key with the
    # SDK; the handler only looks it up.
    get_client(component)
    return CallbackHandler(public_key=credentials_for(component).public_key)


def is_configured(component: Component) -> bool:
    """Whether ``component`` has a usable Langfuse key pair."""
    return credentials_for(component).is_configured


def flush(component: Component) -> None:
    """Flush pending events for one component (call before process exit).

    Tracing is asynchronous, so a short-lived process — a backfill job, an
    experiment run — exits before its spans are sent unless this is called.
    """
    get_client(component).flush()
