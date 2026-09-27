"""``/devices`` router — pairing an edge device to an account, and stopping it.

Three kinds of caller:

- the **device** before it has a token: ``POST /devices/pair`` and
  ``POST /devices/pair/token`` (no auth — the device code is the secret);
- the **device** once paired: ``GET /devices/me`` (``CurrentDevice``);
- the **owner** in the web app: approve a code, list devices, revoke one
  (``CurrentUser``; a superuser sees every device).

Mounted by ``main_web``.
"""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.db import get_session
from core.devices import service
from core.devices.dependencies import CurrentDevice
from core.devices.models import Device
from core.devices.schemas import (
    DeviceRead,
    DeviceToken,
    PairingApprove,
    PairingStart,
    PairingStartRead,
    PairingTokenRequest,
)
from core.users.dependencies import CurrentUser
from core.users.models import User

router = APIRouter(prefix="/devices", tags=["devices"])

SessionDep = Annotated[Session, Depends(get_session)]


def _device_or_404(session: Session, device_id: uuid.UUID, user: User) -> Device:
    device = service.get_device(session, device_id)
    if device is None or not (user.is_superuser or device.owner_id == user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    return device


# --------------------------------------------------------------------------- #
# pairing (RFC 8628 device authorization grant)
# --------------------------------------------------------------------------- #


@router.post(
    "/pair",
    response_model=PairingStartRead,
    summary="Device: ask for a code to show on the display",
)
def start_pairing(payload: PairingStart, session: SessionDep) -> PairingStartRead:
    pairing, device_code = service.start_pairing(session, payload.physical_id)
    return PairingStartRead(
        device_code=device_code,
        user_code=service.format_user_code(pairing.user_code),
        expires_in=int(service.PAIRING_TTL.total_seconds()),
        interval=service.POLL_INTERVAL_SECONDS,
    )


@router.post(
    "/pair/approve",
    response_model=DeviceRead,
    summary="Owner: claim the device showing this code",
    description=(
        "404 if the code is unknown or expired. 409 if the device is still "
        "active under another account — its owner has to revoke it first."
    ),
)
def approve_pairing(payload: PairingApprove, session: SessionDep, user: CurrentUser) -> Device:
    try:
        return service.approve_pairing(session, payload.user_code, owner=user, name=payload.name)
    except service.PairingNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown or expired code") from None
    except service.DeviceOwnedByAnotherUserError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Device is registered to another account"
        ) from None


@router.post(
    "/pair/token",
    response_model=DeviceToken,
    summary="Device: poll until the owner approves, then collect the token",
    description=(
        "Errors carry an RFC 8628 code in `detail`: `authorization_pending` "
        "(400 — wait `interval` seconds and poll again), `expired_token` (400 — "
        "start over with `/devices/pair`), `invalid_grant` (400 — unknown or "
        "already used code). The token never expires; the owner revokes it."
    ),
)
def exchange_token(payload: PairingTokenRequest, session: SessionDep) -> DeviceToken:
    try:
        device, token = service.exchange_device_code(session, payload.device_code)
    except service.PairingPendingError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "authorization_pending") from None
    except service.PairingExpiredError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "expired_token") from None
    except service.InvalidDeviceCodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_grant") from None
    return DeviceToken(access_token=token, device_id=device.id, physical_id=device.physical_id)


# --------------------------------------------------------------------------- #
# devices
# --------------------------------------------------------------------------- #


# Declared before `/{device_id}` so the literal path is not taken for a UUID.
@router.get("/me", response_model=DeviceRead, summary="Device: who am I")
def read_current_device(device: CurrentDevice) -> Device:
    return device


@router.get("", response_model=list[DeviceRead], summary="Owner: my devices")
def list_devices(session: SessionDep, user: CurrentUser) -> Sequence[Device]:
    return service.list_devices(session, owner_id=None if user.is_superuser else user.id)


@router.get("/{device_id}", response_model=DeviceRead)
def get_device(device_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> Device:
    return _device_or_404(session, device_id, user)


@router.post(
    "/{device_id}/revoke",
    response_model=DeviceRead,
    summary="Owner: stop the device (its token is refused from now on)",
)
def revoke_device(device_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> Device:
    return service.revoke_device(session, _device_or_404(session, device_id, user))
