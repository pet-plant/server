"""Request / response models for the ``/devices`` endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PairingStart(BaseModel):
    """Sent by the device when it has no token yet."""

    physical_id: str = Field(min_length=1, max_length=128)


class PairingStartRead(BaseModel):
    #: Secret the device keeps and polls ``/devices/pair/token`` with.
    device_code: str
    #: Short code the device shows on its display, e.g. ``K7QM-4ZPX``.
    user_code: str
    expires_in: int
    #: Seconds the device should wait between polls.
    interval: int


class PairingApprove(BaseModel):
    """Sent by the signed-in owner after reading the code off the device."""

    user_code: str = Field(min_length=4, max_length=16)
    name: str | None = Field(default=None, max_length=120)


class PairingTokenRequest(BaseModel):
    device_code: str = Field(min_length=1, max_length=128)


class DeviceToken(BaseModel):
    #: Long-lived; valid until the owner revokes the device.
    access_token: str
    token_type: str = "bearer"
    device_id: uuid.UUID
    physical_id: str


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    physical_id: str
    owner_id: uuid.UUID
    name: str | None
    status: str  # 'active' | 'revoked'
    paired_at: datetime
    revoked_at: datetime | None
    last_seen_at: datetime | None
    created_at: datetime
