from datetime import timedelta

import jwt
import pytest

from core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_roundtrip() -> None:
    encoded = hash_password("s3cret-passphrase")

    assert encoded != "s3cret-passphrase"
    assert encoded.startswith("pbkdf2_sha256$")
    assert verify_password("s3cret-passphrase", encoded)
    assert not verify_password("wrong", encoded)


def test_hash_password_is_salted() -> None:
    assert hash_password("same") != hash_password("same")


def test_verify_password_rejects_garbage() -> None:
    assert not verify_password("x", "not-a-valid-hash")


def test_access_token_roundtrip() -> None:
    token = create_access_token("user-123", extra_claims={"email": "a@b.com"})
    claims = decode_access_token(token)

    assert claims["sub"] == "user-123"
    assert claims["email"] == "a@b.com"
    assert claims["iss"] == "pet-plant"


def test_expired_token_is_rejected() -> None:
    token = create_access_token("user-123", expires_delta=timedelta(seconds=-1))

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_tampered_token_is_rejected() -> None:
    token = create_access_token("user-123")

    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token + "tampered")
