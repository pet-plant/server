"""Edge-device identity: pairing to an account and device tokens.

Owns the ``auth.devices`` and ``auth.device_pairings`` tables. A device pairs
once through the RFC 8628 device authorization grant (code on its display,
typed by the owner), then stays signed in with its own long-lived token until
the owner revokes it.

Public surface:

- :data:`router` — ``/devices`` endpoints, mounted by ``main_web``.
- :data:`CurrentDevice` / :func:`get_current_device` — FastAPI dependency for
  routes an edge device calls, applied in other contexts' ``api.py``.
- :func:`get_device_by_physical_id` — for ``registry`` to check who a device
  belongs to before binding it to a plant.
"""

from core.devices.api import router
from core.devices.dependencies import CurrentDevice, get_current_device
from core.devices.models import Device
from core.devices.service import get_device_by_physical_id

__all__ = [
    "CurrentDevice",
    "Device",
    "get_current_device",
    "get_device_by_physical_id",
    "router",
]
