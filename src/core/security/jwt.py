"""Encode and decode signed JWT access tokens.

Claims: ``sub`` (subject), ``iat``, ``exp``, ``iss``, ``aud`` — plus any
``extra_claims`` the caller passes (e.g. ``email``, ``role``).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from core.config import get_settings


def create_access_token(
    subject: str,
    *,
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Return a signed access token for ``subject``."""
    settings = get_settings()
    now = datetime.now(UTC)
    ttl = expires_delta or timedelta(seconds=settings.access_token_ttl_seconds)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": now + ttl,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify signature / issuer / audience / expiry and return the claims.

    Raises :class:`jwt.PyJWTError` (or a subclass) when the token is invalid.
    """
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_alg],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )
