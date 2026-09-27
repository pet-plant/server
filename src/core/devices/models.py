"""The ``auth.devices`` and ``auth.device_pairings`` tables.

A **device** is one edge planter, known by the ``physical_id`` it reports
(serial / MAC / provisioning id). Once paired it holds one long-lived bearer
token and stays signed in; the owner stops it by revoking, which takes effect on
the device's next request. Only the token's hash is stored.

A **pairing** is one attempt to attach a device to an account, following the
OAuth 2.0 device authorization grant (RFC 8628): the device asks for a code,
shows the short ``user_code`` on its display, and the owner types that code
into the web app. Seeing the display is what proves the owner has the device in
hand — knowing a serial number printed on the box is not enough.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from core.db import AUTH_SCHEMA, Base


def _now() -> datetime:
    return datetime.now(UTC)


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = {"schema": AUTH_SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    physical_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{AUTH_SCHEMA}.users.id"), nullable=False, index=True
    )
    name: Mapped[str | None] = mapped_column(String(120))
    # 'active' | 'revoked'
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # SHA-256 of the device's bearer token; NULL between approval and pickup,
    # and after a revoke.
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    paired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Device {self.physical_id} {self.status}>"


class DevicePairing(Base):
    __tablename__ = "device_pairings"
    __table_args__ = {"schema": AUTH_SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    physical_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # Shown on the device, typed by the owner. Stored normalised (no dash).
    user_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # SHA-256 of the secret the device polls with.
    device_code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # 'pending' | 'approved' | 'consumed' | 'expired'
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(f"{AUTH_SCHEMA}.devices.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
