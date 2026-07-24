"""HTTP-level tests for the AI router (/api/v1/ai/*). Runs against the
default stub provider (zero configuration, no network) -- see
tests/test_ai_providers.py for provider-internal tests and
tests/test_dynamic_rule_source.py for the subprocess-level pattern used
elsewhere in this project when a genuinely different process config is
required.

Structural safety is asserted directly, not just described in a
docstring: generate-rule must never create/modify anything in
rule_pack_repository."""

import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.settings import get_settings
from app.application.use_cases.register_user import RegisterUserUseCase
from app.infrastructure.ai.common import AIProviderError
from app.interfaces.api.dependencies import (
    user_repository, role_repository, rule_pack_repository,
    generate_rule_from_description_use_case, create_rule_pack_use_case,
)
from app.application.use_cases.manage_rules import CreateRuleUseCase
from app.interfaces.api.dependencies import audit_log_repository

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


# -- generate-rule ----------------------------------------------------------

def test_generate_rule_returns_draft_without_persisting_anything():
    before = len(rule_pack_repository.list_all(include_archived=True, limit=10_000))

    resp = client.post("/api/v1/ai/generate-rule", json={
        "description": "If affected users is greater than 5000, mark priority critical",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["aiProvider"] == "stub"
    assert body["isValid"] is True
    assert body["rule"]["conditions"] == {">": [{"var": "affectedUsers"}, 5000]}

    after = len(rule_pack_repository.list_all(include_archived=True, limit=10_000))
    assert after == before  # no rule pack was created/modified by generating a draft


def test_generate_rule_rejects_empty_description():
    resp = client.post("/api/v1/ai/generate-rule", json={"description": ""})
    assert resp.status_code == 422  # pydantic min_length


def test_generate_rule_surfaces_ai_provider_error_as_502(monkeypatch):
    class BoomProvider:
        def generate_rule(self, *a, **kw):
            raise AIProviderError("simulated upstream failure")

    original = generate_rule_from_description_use_case.ai_provider
    generate_rule_from_description_use_case.ai_provider = BoomProvider()
    try:
        resp = client.post("/api/v1/ai/generate-rule", json={"description": "anything"})
        assert resp.status_code == 502
        assert "simulated upstream failure" in resp.json()["detail"]
    finally:
        generate_rule_from_description_use_case.ai_provider = original


# -- document-rule ------------------------------------------------------

def test_document_rule_with_inline_payload():
    resp = client.post("/api/v1/ai/document-rule", json={"rule": {
        "ruleCode": "R1", "name": "Test rule", "conditions": {">": [{"var": "x"}, 1]}, "actions": {"priority": "High"},
    }})
    assert resp.status_code == 200
    assert "Test rule" in resp.json()["documentation"]


def test_document_rule_with_existing_rule_id():
    pack = create_rule_pack_use_case.execute(name=_unique("docpack"), actor="test")
    rule = CreateRuleUseCase(rule_pack_repository, audit_log_repository).execute(
        pack.id, {"ruleCode": "DOC1", "name": "Doc rule", "conditions": {"==": [{"var": "x"}, 1]}, "actions": {}}, actor="test",
    )
    resp = client.post("/api/v1/ai/document-rule", json={"ruleId": rule.id})
    assert resp.status_code == 200
    assert "Doc rule" in resp.json()["documentation"]


def test_document_rule_requires_one_of_ruleid_or_rule():
    resp = client.post("/api/v1/ai/document-rule", json={})
    assert resp.status_code == 400


def test_document_rule_missing_rule_id_404():
    resp = client.post("/api/v1/ai/document-rule", json={"ruleId": "does-not-exist"})
    assert resp.status_code == 404


# -- explain-decision ------------------------------------------------------

def test_explain_decision_returns_both_explanations():
    incident_id = _unique("INC")
    client.post("/api/v1/incidents/evaluate", json={"incidentId": incident_id, "affectedUsers": 20000, "vipCustomersAffected": True})

    resp = client.post(f"/api/v1/ai/explain-decision/{incident_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deterministicExplanation"]
    assert body["aiExplanation"]
    assert body["aiProvider"] == "stub"


def test_explain_decision_404_when_no_decision_exists():
    resp = client.post("/api/v1/ai/explain-decision/does-not-exist")
    assert resp.status_code == 404


# -- RBAC --------------------------------------------------------------------

def test_editor_can_generate_and_document_but_not_explain_decision(auth_required_on):
    editor_headers = _bearer_for("editor")

    resp = client.post("/api/v1/ai/generate-rule", json={"description": "test"}, headers=editor_headers)
    assert resp.status_code == 200

    resp = client.post("/api/v1/ai/document-rule", json={"rule": {"name": "x", "conditions": {}, "actions": {}, "ruleCode": "X"}}, headers=editor_headers)
    assert resp.status_code == 200

    incident_id = _unique("INC-RBAC")
    client.post("/api/v1/incidents/evaluate", json={"incidentId": incident_id})
    resp = client.post(f"/api/v1/ai/explain-decision/{incident_id}", headers=editor_headers)
    assert resp.status_code == 403  # editor lacks decisions:read


def test_viewer_cannot_generate_rule(auth_required_on):
    viewer_headers = _bearer_for("viewer")
    resp = client.post("/api/v1/ai/generate-rule", json={"description": "test"}, headers=viewer_headers)
    assert resp.status_code == 403  # viewer lacks rules:edit
