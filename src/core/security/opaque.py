"""Opaque bearer secrets: random strings the server only ever stores hashed.

Used where a credential must be revocable at any moment (device tokens, pairing
codes): the server looks the hash up on every request, so deleting it takes
effect immediately — unlike a JWT, which stays valid until it expires.

SHA-256 without a salt is enough here: the secrets are 256 bits of randomness,
not human-chosen passwords, so there is nothing to brute-force.
"""

import hashlib
import secrets


def new_opaque_token(prefix: str = "") -> str:
    """A fresh URL-safe secret (256 bits), optionally tagged with ``prefix``."""
    return f"{prefix}{secrets.token_urlsafe(32)}"


def hash_opaque_token(token: str) -> str:
    """The hex SHA-256 of ``token`` — what gets stored and looked up."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
