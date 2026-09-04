"""User identity + JWT authentication (owns the ``auth.users`` table).

Kept deliberately small: it exists for authentication and for anchoring plant
ownership in the ``registry`` context via :attr:`User.id`.

Public surface:

- :data:`router` — ``/auth`` endpoints (register / token / me), mounted by
  ``main_web``.
- :func:`get_current_user`, :func:`get_current_active_user`,
  :func:`get_current_superuser` — FastAPI dependencies other contexts apply in
  their own ``api.py``.
- :func:`ensure_admin_user` — seed / reconcile the bootstrap admin on startup.
"""

from core.users.api import router
from core.users.dependencies import (
    CurrentSuperuser,
    CurrentUser,
    get_current_active_user,
    get_current_superuser,
    get_current_user,
)
from core.users.models import User
from core.users.service import ensure_admin_user

__all__ = [
    "CurrentSuperuser",
    "CurrentUser",
    "User",
    "ensure_admin_user",
    "get_current_active_user",
    "get_current_superuser",
    "get_current_user",
    "router",
]
