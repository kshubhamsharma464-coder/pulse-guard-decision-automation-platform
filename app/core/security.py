"""Password hashing and JWT issuance/verification -- the primitives RBAC
and JWT auth (app/interfaces/api/security.py) build on.

Password hashing uses PBKDF2-HMAC-SHA256 from the stdlib `hashlib`
(310,000 iterations, OWASP's 2023 minimum for PBKDF2-SHA256) rather than
bcrypt/argon2 -- a deliberate choice to avoid a C-extension dependency
(bcrypt/argon2-cffi) that can fail to build in restricted environments,
not a security downgrade: PBKDF2-SHA256 is still an approved, unbroken
KDF (NIST SP 800-63B) and is what Django uses by default. Swapping to
argon2id later is a one-function change (`hash_password`/`verify_password`
are the only two call sites in the codebase) if the extra dependency is
ever acceptable.

JWTs use PyJWT (HS256, symmetric -- `Settings.jwt_secret`). Access tokens
are short-lived (15 min default) and carry `sub` (user id), `roles`, and
`type: "access"`; refresh tokens are long-lived (7 days default), carry
only `sub` and `type: "refresh"`, and are never accepted where an access
token is expected (verify_token() checks the `type` claim)."""

import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import jwt

_PBKDF2_ITERATIONS = 310_000
_PBKDF2_ALGO = "sha256"


def hash_password(plain_password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac(_PBKDF2_ALGO, plain_password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(plain_password: str, hashed: str) -> bool:
    try:
        scheme, iterations, salt_hex, hash_hex = hashed.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    derived = hashlib.pbkdf2_hmac(_PBKDF2_ALGO, plain_password.encode("utf-8"), salt, int(iterations))
    return hmac.compare_digest(derived, expected)


def generate_api_key() -> str:
    """Raw API key shown to the caller exactly once. Prefixed so it's
    recognizable in logs/config without exposing the secret portion."""
    return f"tdo_{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    # Same PBKDF2 scheme as passwords -- an API key is just a very long,
    # machine-generated password.
    return hash_password(raw_key)


def verify_api_key(raw_key: str, hashed: str) -> bool:
    return verify_password(raw_key, hashed)


def create_access_token(*, subject: str, roles: List[str], secret: str, algorithm: str, expires_minutes: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "roles": roles,
        "type": "access",
        "jti": uuid.uuid4().hex,  # unique per token -- also what a future revocation list would key on
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def create_refresh_token(*, subject: str, secret: str, algorithm: str, expires_days: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": "refresh",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(days=expires_days),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_token(token: str, *, secret: str, algorithm: str, expected_type: Optional[str] = None) -> Dict[str, Any]:
    """Raises jwt.PyJWTError (ExpiredSignatureError, InvalidTokenError, ...)
    on any failure -- callers (app/interfaces/api/security.py) translate
    that into an HTTP 401, never let it propagate as a 500."""
    payload = jwt.decode(token, secret, algorithms=[algorithm])
    if expected_type is not None and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected a '{expected_type}' token, got '{payload.get('type')}'")
    return payload
