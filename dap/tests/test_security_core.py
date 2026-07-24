"""Unit tests for app/core/security.py's primitives, independent of any
HTTP layer -- password hashing, API key generation/hashing, JWT issuance
and the access/refresh type guard."""

import time
import jwt as pyjwt
import pytest
from app.core.security import (
    hash_password, verify_password, generate_api_key, hash_api_key, verify_api_key,
    create_access_token, create_refresh_token, decode_token,
)


def test_password_hash_roundtrip_and_salted():
    h1 = hash_password("correct horse battery staple")
    h2 = hash_password("correct horse battery staple")
    assert h1 != h2  # different salt each time
    assert verify_password("correct horse battery staple", h1)
    assert verify_password("correct horse battery staple", h2)
    assert not verify_password("wrong password", h1)


def test_verify_password_rejects_garbage_hash():
    assert verify_password("anything", "not-a-real-hash") is False


def test_api_key_generation_and_hashing():
    raw = generate_api_key()
    assert raw.startswith("tdo_")
    hashed = hash_api_key(raw)
    assert verify_api_key(raw, hashed)
    assert not verify_api_key(generate_api_key(), hashed)


def test_access_token_roundtrip():
    token = create_access_token(subject="user-1", roles=["admin"], secret="s", algorithm="HS256", expires_minutes=5)
    payload = decode_token(token, secret="s", algorithm="HS256", expected_type="access")
    assert payload["sub"] == "user-1"
    assert payload["roles"] == ["admin"]
    assert "jti" in payload


def test_refresh_token_rejected_as_access_token():
    token = create_refresh_token(subject="user-1", secret="s", algorithm="HS256", expires_days=1)
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_token(token, secret="s", algorithm="HS256", expected_type="access")


def test_expired_access_token_rejected():
    token = create_access_token(subject="user-1", roles=[], secret="s", algorithm="HS256", expires_minutes=0)
    time.sleep(1.1)
    with pytest.raises(pyjwt.ExpiredSignatureError):
        decode_token(token, secret="s", algorithm="HS256", expected_type="access")


def test_wrong_secret_rejected():
    token = create_access_token(subject="user-1", roles=[], secret="s1", algorithm="HS256", expires_minutes=5)
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_token(token, secret="s2", algorithm="HS256", expected_type="access")
