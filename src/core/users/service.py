"""User persistence and credential checks — no HTTP concerns here."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import get_settings
from core.security import hash_password, verify_password
from core.users.models import User
from core.users.schemas import UserCreate

logger = logging.getLogger(__name__)


class UserAlreadyExistsError(Exception):
    """Raised when registering an email that is already taken."""


def get_user_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email.lower()))


def create_user(session: Session, data: UserCreate, *, is_superuser: bool = False) -> User:
    if get_user_by_email(session, data.email) is not None:
        raise UserAlreadyExistsError(data.email)

    user = User(
        email=data.email.lower(),
        name=data.name,
        hashed_password=hash_password(data.password),
        is_superuser=is_superuser,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def ensure_admin_user(session: Session) -> User:
    """Create the bootstrap admin from settings, or promote it if it exists.

    Idempotent: safe to call on every web startup. An existing account at
    ``ADMIN_EMAIL`` is reactivated, marked superuser, and has its password reset
    to the configured one so the credentials in the environment always work.
    """
    settings = get_settings()
    email = settings.admin_email.lower()

    user = get_user_by_email(session, email)
    if user is None:
        user = create_user(
            session,
            UserCreate(
                email=email,
                name=settings.admin_name,
                password=settings.admin_password,
            ),
            is_superuser=True,
        )
        logger.info("Seeded bootstrap admin account %s", email)
        return user

    user.name = settings.admin_name
    user.hashed_password = hash_password(settings.admin_password)
    user.is_active = True
    user.is_superuser = True
    session.commit()
    session.refresh(user)
    logger.info("Reconciled bootstrap admin account %s", email)
    return user


def authenticate_user(session: Session, email: str, password: str) -> User | None:
    """Return the user when ``email`` / ``password`` match, else ``None``."""
    user = get_user_by_email(session, email)
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user
