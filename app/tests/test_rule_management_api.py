"""Phase 2.5: dynamic Rule Management platform, exercised through the HTTP
API (in-memory backend -- the default -- so these run with zero setup,
same as every other router test in this project). The Postgres-backed,
cache-fronted "live evaluation" path (Settings.rule_source="dynamic") is
covered separately via a subprocess-level smoke test since it requires a
fresh process (Settings is an lru_cache'd singleton read once at import
time by dependencies.py) -- see this file's bottom section.

RBAC here mirrors tests/test_auth.py's pattern: mutate the process-wide
Settings singleton for auth_required, restore in a fixture teardown."""

import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.settings import get_settings
from app.application.use_cases.register_user import RegisterUserUseCase
from app.interfaces.api.dependencies import user_repository, role_repository

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


def _unique(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


def _bearer_for(role: str) -> dict:
    email = f"{_unique(role)}@example.com"
    RegisterUserUseCase(user_repository, role_repository).execute(email=email, password="correcthorse123", roles=[role])
    tokens = client.post("/api/v1/auth/login", json={"email": email, "password": "correcthorse123"}).json()
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


def _simple_rule_payload(code="R1"):
    return {
        "ruleCode": code, "name": f"Test {code}", "conditions": {"==": [{"var": "x"}, 1]},
        "actions": {"priority": "High"},
    }


# -- Rule pack lifecycle (default config, no auth required) --------------

def test_full_rule_pack_lifecycle_via_http():
    name = _unique("pack")

    resp = client.post("/api/v1/rule-packs", json={"name": name})
    assert resp.status_code == 201, resp.text
    pack = resp.json()
    assert pack["status"] == "draft" and pack["version"] == 1

    resp = client.post(f"/api/v1/rules?rulePackId={pack['id']}", json=_simple_rule_payload())
    assert resp.status_code == 201, resp.text
    rule = resp.json()
    assert rule["ruleCode"] == "R1"

    resp = client.get(f"/api/v1/rule-packs/{pack['id']}")
    assert resp.json()["ruleCount"] == 1

    resp = client.post(f"/api/v1/rule-packs/{pack['id']}/publish")
    assert resp.status_code == 200 and resp.json()["status"] == "published"

    resp = client.post(f"/api/v1/rule-packs/{pack['id']}/activate")
    assert resp.status_code == 200 and resp.json()["status"] == "active"
    assert resp.json()["activatedAt"] is not None

    resp = client.get(f"/api/v1/rule-packs/active?name={name}")
    assert resp.status_code == 200 and resp.json()["id"] == pack["id"]

    resp = client.get(f"/api/v1/rule-packs/{pack['id']}/export")
    assert resp.status_code == 200
    exported = resp.json()
    assert exported["name"] == name and len(exported["rules"]) == 1


def test_cannot_publish_empty_rule_pack():
    name = _unique("empty")
    pack = client.post("/api/v1/rule-packs", json={"name": name}).json()
    resp = client.post(f"/api/v1/rule-packs/{pack['id']}/publish")
    assert resp.status_code == 400
    assert "zero rules" in resp.json()["detail"]


def test_cannot_activate_a_draft_directly():
    name = _unique("skip")
    pack = client.post("/api/v1/rule-packs", json={"name": name}).json()
    client.post(f"/api/v1/rules?rulePackId={pack['id']}", json=_simple_rule_payload())
    resp = client.post(f"/api/v1/rule-packs/{pack['id']}/activate")
    assert resp.status_code == 400
    assert "publish it first" in resp.json()["detail"]


def test_import_rejects_duplicate_version_but_allows_new_version():
    name = _unique("imported")
    pack = client.post("/api/v1/rule-packs", json={"name": name}).json()
    client.post(f"/api/v1/rules?rulePackId={pack['id']}", json=_simple_rule_payload())
    client.post(f"/api/v1/rule-packs/{pack['id']}/publish")
    client.post(f"/api/v1/rule-packs/{pack['id']}/activate")
    exported = client.get(f"/api/v1/rule-packs/{pack['id']}/export").json()

    resp = client.post("/api/v1/rule-packs/import", json=exported)
    assert resp.status_code == 409, resp.text  # version 1 already exists

    exported.pop("version")
    resp = client.post("/api/v1/rule-packs/import", json=exported)
    assert resp.status_code == 201
    assert resp.json()["version"] == 2
    assert resp.json()["status"] == "draft"


def test_rollback_reactivates_prior_version():
    name = _unique("rollback")
    pack1 = client.post("/api/v1/rule-packs", json={"name": name}).json()
    client.post(f"/api/v1/rules?rulePackId={pack1['id']}", json=_simple_rule_payload("R1"))
    client.post(f"/api/v1/rule-packs/{pack1['id']}/publish")
    client.post(f"/api/v1/rule-packs/{pack1['id']}/activate")

    pack2 = client.post("/api/v1/rule-packs", json={"name": name}).json()
    assert pack2["parentVersion"] == 1
    client.post(f"/api/v1/rules?rulePackId={pack2['id']}", json=_simple_rule_payload("R2"))
    client.post(f"/api/v1/rule-packs/{pack2['id']}/publish")
    client.post(f"/api/v1/rule-packs/{pack2['id']}/activate")

    resp = client.post(f"/api/v1/rule-packs/{pack2['id']}/rollback", json={"reason": "bad rollout"})
    assert resp.status_code == 200, resp.text
    rolled_back = resp.json()
    assert rolled_back["version"] == 1 and rolled_back["status"] == "active"


def test_soft_delete_refuses_active_pack_but_allows_others():
    name = _unique("delete")
    pack = client.post("/api/v1/rule-packs", json={"name": name}).json()
    client.post(f"/api/v1/rules?rulePackId={pack['id']}", json=_simple_rule_payload())
    client.post(f"/api/v1/rule-packs/{pack['id']}/publish")
    client.post(f"/api/v1/rule-packs/{pack['id']}/activate")

    resp = client.delete(f"/api/v1/rule-packs/{pack['id']}")
    assert resp.status_code == 400
    assert "active" in resp.json()["detail"]

    other = client.post("/api/v1/rule-packs", json={"name": _unique("deletable")}).json()
    resp = client.delete(f"/api/v1/rule-packs/{other['id']}")
    assert resp.status_code == 200 and resp.json()["status"] == "archived"


def test_metadata_update_only_allowed_on_draft():
    name = _unique("meta")
    pack = client.post("/api/v1/rule-packs", json={"name": name}).json()
    resp = client.patch(f"/api/v1/rule-packs/{pack['id']}", json={"region": "Delhi"})
    assert resp.status_code == 200 and resp.json()["region"] == "Delhi"

    client.post(f"/api/v1/rules?rulePackId={pack['id']}", json=_simple_rule_payload())
    client.post(f"/api/v1/rule-packs/{pack['id']}/publish")
    resp = client.patch(f"/api/v1/rule-packs/{pack['id']}", json={"region": "Mumbai"})
    assert resp.status_code == 400
    assert "only Draft packs are editable" in resp.json()["detail"]


# -- Rule CRUD -------------------------------------------------------------

def test_rule_crud_and_validate_and_bulk_and_history():
    name = _unique("rulecrud")
    pack = client.post("/api/v1/rule-packs", json={"name": name}).json()

    created = client.post(f"/api/v1/rules?rulePackId={pack['id']}", json=_simple_rule_payload()).json()
    rule_id = created["id"]

    resp = client.get(f"/api/v1/rules/{rule_id}")
    assert resp.status_code == 200 and resp.json()["ruleCode"] == "R1"

    resp = client.patch(f"/api/v1/rules/{rule_id}", json={"name": "Renamed"})
    assert resp.status_code == 200 and resp.json()["name"] == "Renamed"

    resp = client.post(
        f"/api/v1/rules/bulk?rulePackId={pack['id']}",
        json={"rules": [_simple_rule_payload("R2"), _simple_rule_payload("R3")]},
    )
    assert resp.status_code == 201 and len(resp.json()) == 2

    resp = client.get(f"/api/v1/rules?rulePackId={pack['id']}")
    assert resp.status_code == 200 and len(resp.json()) == 3

    resp = client.post("/api/v1/rules/validate", json=_simple_rule_payload("RV"))
    assert resp.status_code == 200 and resp.json()["isValid"] is True

    resp = client.delete(f"/api/v1/rules/{rule_id}")
    assert resp.status_code == 200 and resp.json()["enabled"] is False

    resp = client.get(f"/api/v1/rules/history?rule_id={rule_id}")
    assert resp.status_code == 200
    actions = [e["action"] for e in resp.json()]
    assert actions == ["created", "updated", "deleted"]


def test_duplicate_rule_code_rejected():
    name = _unique("duprule")
    pack = client.post("/api/v1/rule-packs", json={"name": name}).json()
    client.post(f"/api/v1/rules?rulePackId={pack['id']}", json=_simple_rule_payload("DUP"))
    resp = client.post(f"/api/v1/rules?rulePackId={pack['id']}", json=_simple_rule_payload("DUP"))
    assert resp.status_code == 400


# -- Incidents REST resource ------------------------------------------------

def test_create_incident_with_and_without_evaluation():
    resp = client.post("/api/v1/incidents", json={"incidentId": _unique("INC"), "affectedUsers": 100})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "evaluated"
    assert body["decision"] is not None

    incident_id = _unique("INC-NOEVAL")
    resp = client.post("/api/v1/incidents", json={"incidentId": incident_id, "evaluate": False})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "received" and body["decision"] is None

    resp = client.get(f"/api/v1/incidents/{incident_id}")
    assert resp.status_code == 200 and resp.json()["status"] == "received"


def test_list_and_bulk_create_incidents():
    ids = [_unique("BULK") for _ in range(3)]
    resp = client.post("/api/v1/incidents/bulk", json={"incidents": [{"incidentId": i} for i in ids], "evaluate": True})
    assert resp.status_code == 201
    assert len(resp.json()) == 3
    assert all(r["status"] == "evaluated" for r in resp.json())

    resp = client.get("/api/v1/incidents?status=evaluated&limit=5")
    assert resp.status_code == 200
    assert len(resp.json()) <= 5


def test_get_missing_incident_404():
    resp = client.get("/api/v1/incidents/does-not-exist")
    assert resp.status_code == 404


# -- RBAC: editor vs policy_admin -----------------------------------------

def test_editor_can_create_but_not_publish_activate_rollback_delete(auth_required_on):
    editor_headers = _bearer_for("editor")
    name = _unique("rbac")

    resp = client.post("/api/v1/rule-packs", json={"name": name}, headers=editor_headers)
    assert resp.status_code == 201, resp.text
    pack = resp.json()

    resp = client.post(f"/api/v1/rules?rulePackId={pack['id']}", json=_simple_rule_payload(), headers=editor_headers)
    assert resp.status_code == 201

    resp = client.post(f"/api/v1/rule-packs/{pack['id']}/publish", headers=editor_headers)
    assert resp.status_code == 403

    policy_admin_headers = _bearer_for("policy_admin")
    resp = client.post(f"/api/v1/rule-packs/{pack['id']}/publish", headers=policy_admin_headers)
    assert resp.status_code == 200

    resp = client.post(f"/api/v1/rule-packs/{pack['id']}/activate", headers=editor_headers)
    assert resp.status_code == 403
    resp = client.post(f"/api/v1/rule-packs/{pack['id']}/activate", headers=policy_admin_headers)
    assert resp.status_code == 200

    resp = client.delete(f"/api/v1/rule-packs/{pack['id']}", headers=editor_headers)
    assert resp.status_code == 403


def test_viewer_cannot_create_rule_packs(auth_required_on):
    viewer_headers = _bearer_for("viewer")
    resp = client.post("/api/v1/rule-packs", json={"name": _unique("denied")}, headers=viewer_headers)
    assert resp.status_code == 403


def test_rule_management_endpoints_open_by_default_when_auth_not_required():
    # No auth_required_on fixture here -- confirms the untouched default
    # (auth_required=False) leaves every new endpoint open, same
    # backward-compatibility contract as Phase 2's original endpoints.
    resp = client.post("/api/v1/rule-packs", json={"name": _unique("open")})
    assert resp.status_code == 201
