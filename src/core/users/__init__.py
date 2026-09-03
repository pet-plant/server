"""User identity + JWT authentication (owns the ``auth.users`` table).

Kept deliberately small: it exists for authentication and for anchoring plant
ownership in the ``registry`` context via :attr:`User.id`.

Public surface:

- :data:`router` — ``/auth`` endpoints (register / token / me), mounted by
  ``main_web``.
- :func:`get_current_user`, :func:`get_current_active_user` — FastAPI
  dependencies other contexts apply in their own ``api.py``.
"""

from core.users.api import router
from core.users.dependencies import CurrentUser, get_current_active_user, get_current_user
from core.users.models import User

__all__ = [
    "CurrentUser",
    "User",
    "get_current_active_user",
    "get_current_user",
    "router",
]
