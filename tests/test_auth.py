"""Phase 2: auth & RBAC. Split into two groups --

1. Default-config tests (auth_required=False, the untouched default):
   prove every existing unauthenticated flow still works, AND that the
   new /api/v1/auth/* endpoints work standalone.
2. auth_required=True tests: prove RBAC is actually enforced once an
   operator opts in -- mutates the process-wide (lru_cache'd) Settings
   singleton for the duration of the test and restores it in a finally
   block, since Settings isn't re-read per-request (see app/core/settings.py)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.settings import get_settings
from app.interfaces.api.dependencies import user_repository, role_repository, api_key_repository

client = TestClient(app)


@pytest.fixture()
def auth_required_on():
    settings = get_settings()
    original = settings.auth_required
    settings.auth_required = True
    try:
        yield settings
    finally:
        settings.auth_required = original


def _unique_email(label: str) -> str:
    import uuid
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


# -- Registration / login / refresh / me --------------------------------

def test_register_and_login():
    email = _unique_email("alice")
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": "correcthorse123", "fullName": "Alice"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == email
    assert body["roles"] == ["viewer"]  # least-privilege default

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "correcthorse123"})
    assert resp.status_code == 200, resp.text
    tokens = resp.json()
    assert tokens["tokenType"] == "bearer"
    assert tokens["accessToken"] and tokens["refreshToken"]


def test_register_duplicate_email_rejected():
    email = _unique_email("dup")
    client.post("/api/v1/auth/register", json={"email": email, "password": "correcthorse123"})
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": "anotherpassword1"})
    assert resp.status_code == 400


def test_register_unknown_role_rejected():
    resp = client.post("/api/v1/auth/register", json={
        "email": _unique_email("badrole"), "password": "correcthorse123", "roles": ["superadmin-does-not-exist"],
    })
    assert resp.status_code == 400


def test_login_wrong_password_rejected():
    email = _unique_email("bob")
    client.post("/api/v1/auth/register", json={"email": email, "password": "correcthorse123"})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "wrongpassword"})
    assert resp.status_code == 401


def test_me_requires_credentials():
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_returns_current_user():
    email = _unique_email("carol")
    client.post("/api/v1/auth/register", json={"email": email, "password": "correcthorse123", "fullName": "Carol"})
    tokens = client.post("/api/v1/auth/login", json={"email": email, "password": "correcthorse123"}).json()

    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['accessToken']}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == email


def test_refresh_issues_new_tokens():
    email = _unique_email("dave")
    client.post("/api/v1/auth/register", json={"email": email, "password": "correcthorse123"})
    tokens = client.post("/api/v1/auth/login", json={"email": email, "password": "correcthorse123"}).json()

    resp = client.post("/api/v1/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["accessToken"] != tokens["accessToken"]


def test_refresh_rejects_an_access_token():
    email = _unique_email("erin")
    client.post("/api/v1/auth/register", json={"email": email, "password": "correcthorse123"})
    tokens = client.post("/api/v1/auth/login", json={"email": email, "password": "correcthorse123"}).json()

    # Passing an access token where a refresh token is expected must fail --
    # proves decode_token()'s expected_type check actually does something.
    resp = client.post("/api/v1/auth/refresh", json={"refreshToken": tokens["accessToken"]})
    assert resp.status_code == 401


def test_invalid_bearer_token_rejected():
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


# -- API keys -------------------------------------------------------------

def test_create_api_key_endpoint_is_no_longer_supported():
    email = _unique_email("admin")
    from app.application.use_cases.register_user import RegisterUserUseCase
    from app.interfaces.api.dependencies import role_repository as _roles
    RegisterUserUseCase(user_repository, _roles).execute(email=email, password="correcthorse123", roles=["admin"])
    tokens = client.post("/api/v1/auth/login", json={"email": email, "password": "correcthorse123"}).json()

    resp = client.post(
        "/api/v1/auth/api-keys",
        json={"name": "test key", "roles": ["operator"]},
        headers={"Authorization": f"Bearer {tokens['accessToken']}"},
    )
    assert resp.status_code == 404


def test_create_api_key_endpoint_requires_jwt_only_when_auth_required(auth_required_on):
    email = _unique_email("vieweronly")
    client.post("/api/v1/auth/register", json={"email": email, "password": "correcthorse123"})
    tokens = client.post("/api/v1/auth/login", json={"email": email, "password": "correcthorse123"}).json()

    resp = client.post(
        "/api/v1/auth/api-keys",
        json={"name": "should fail"},
        headers={"Authorization": f"Bearer {tokens['accessToken']}"},
    )
    assert resp.status_code == 404


# -- Backward compatibility: default config leaves existing flow open -----

def test_evaluate_incident_still_open_without_credentials_by_default(inc_101_payload):
    resp = client.post("/api/v1/incidents/evaluate", json=inc_101_payload)
    assert resp.status_code == 200


# -- RBAC actually enforced once auth_required=True ------------------------

def test_evaluate_incident_requires_auth_when_enabled(auth_required_on, inc_101_payload):
    resp = client.post("/api/v1/incidents/evaluate", json=inc_101_payload)
    assert resp.status_code == 401


def test_evaluate_incident_with_valid_token_and_permission_when_auth_required(auth_required_on, inc_101_payload):
    email = _unique_email("operator")
    from app.application.use_cases.register_user import RegisterUserUseCase
    RegisterUserUseCase(user_repository, role_repository).execute(email=email, password="correcthorse123", roles=["operator"])
    tokens = client.post("/api/v1/auth/login", json={"email": email, "password": "correcthorse123"}).json()

    resp = client.post(
        "/api/v1/incidents/evaluate", json=inc_101_payload,
        headers={"Authorization": f"Bearer {tokens['accessToken']}"},
    )
    assert resp.status_code == 200


def test_evaluate_incident_with_viewer_role_forbidden_when_auth_required(auth_required_on, inc_101_payload):
    email = _unique_email("readonly")
    client.post("/api/v1/auth/register", json={"email": email, "password": "correcthorse123"})  # viewer, no incidents:evaluate
    tokens = client.post("/api/v1/auth/login", json={"email": email, "password": "correcthorse123"}).json()

    resp = client.post(
        "/api/v1/incidents/evaluate", json=inc_101_payload,
        headers={"Authorization": f"Bearer {tokens['accessToken']}"},
    )
    assert resp.status_code == 403


def test_api_key_flow_is_not_supported(auth_required_on, inc_101_payload):
    resp = client.post(
        "/api/v1/incidents/evaluate", json=inc_101_payload, headers={"X-API-Key": "tdo_dummy"},
    )
    assert resp.status_code == 401
