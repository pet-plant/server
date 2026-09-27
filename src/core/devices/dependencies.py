"""FastAPI dependency for device-authenticated routes.

Edge devices send ``Authorization: Bearer ppd_…`` — their own long-lived token,
never an owner's. Routes a device calls (capture upload, presentation sync, …)
take :data:`CurrentDevice`; routes a person calls keep using ``CurrentUser``.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from core.db import get_session
from core.devices.models import Device
from core.devices.service import authenticate_device

device_bearer = HTTPBearer(auto_error=False, scheme_name="DeviceToken")


def get_current_device(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(device_bearer)],
    session: Annotated[Session, Depends(get_session)],
) -> Device:
    device = (
        authenticate_device(session, credentials.credentials) if credentials else None
    )
    if device is None:
        # Also what a revoked device sees: re-pairing is the only way back.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked device token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return device


CurrentDevice = Annotated[Device, Depends(get_current_device)]
"""The signed-in edge device, for route signatures in other contexts' ``api.py``."""
