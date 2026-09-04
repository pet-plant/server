"""FastAPI auth dependencies other contexts inject via ``Depends``.

``oauth2_scheme`` points at ``POST /auth/token`` (form login), which is what
makes the **Authorize** button in ``/docs`` work once the router is mounted.
"""

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from core.db import get_session
from core.security import decode_access_token
from core.users.models import User
from core.users.service import get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise _credentials_exc from None

    subject = payload.get("sub")
    if subject is None:
        raise _credentials_exc
    try:
        user_id = uuid.UUID(str(subject))
    except ValueError:
        raise _credentials_exc from None

    user = get_user_by_id(session, user_id)
    if user is None:
        raise _credentials_exc
    return user


def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user


def get_current_superuser(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough privileges"
        )
    return current_user


CurrentUser = Annotated[User, Depends(get_current_active_user)]
"""Convenience alias for route signatures in other contexts' ``api.py``."""

CurrentSuperuser = Annotated[User, Depends(get_current_superuser)]
"""Like :data:`CurrentUser`, but 403s unless the caller is an admin."""
