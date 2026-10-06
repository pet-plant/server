"""Care actions: the log of care the owner reports doing.

The GUI shows one completion button per step of a ``companion`` care plan, and
a watering button whether or not the plant has a problem. Each press is
appended to ``action.care_event``; nothing is updated in place. Owns the
``action`` Postgres schema.

Public surface:

- :data:`router` — the ``/action`` endpoints (record an event, care plan
  progress), mounted by ``main_web``.
- :func:`list_care_events` — in-process interface for the other contexts
  (``advice``); events come back as :class:`CareEventRead`.
"""

from action.api import router
from action.interface import list_care_events
from action.schemas import CareEventRead, CareEventType

__all__ = ["CareEventRead", "CareEventType", "list_care_events", "router"]
