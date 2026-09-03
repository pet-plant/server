"""Cross-cutting crypto primitives: password hashing and JWT access tokens.

Pure mechanism — no knowledge of users, roles or the database. The ``users``
package builds the authentication policy on top of this.
"""

from core.security.jwt import create_access_token, decode_access_token
from core.security.password import hash_password, verify_password

__all__ = [
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
]
