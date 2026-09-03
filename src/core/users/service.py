"""User persistence and credential checks — no HTTP concerns here."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.security import hash_password, verify_password
from core.users.models import User
from core.users.schemas import UserCreate


class UserAlreadyExistsError(Exception):
    """Raised when registering an email that is already taken."""


def get_user_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email.lower()))


def create_user(session: Session, data: UserCreate) -> User:
    if get_user_by_email(session, data.email) is not None:
        raise UserAlreadyExistsError(data.email)

    user = User(
        email=data.email.lower(),
        name=data.name,
        hashed_password=hash_password(data.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate_user(session: Session, email: str, password: str) -> User | None:
    """Return the user when ``email`` / ``password`` match, else ``None``."""
    user = get_user_by_email(session, email)
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user
