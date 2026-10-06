"""Care actions: the log of care the owner reports doing.

The GUI shows one completion button per step of a ``companion`` care plan, and
a watering button whether or not the plant has a problem. Each press is
appended to ``action.care_event``; nothing is updated in place. Owns the
``action`` Postgres schema.

Public surface:

- :data:`router` — the ``/action`` endpoints (record an event), mounted by
  ``main_web``.
"""

from action.api import router

__all__ = ["router"]
