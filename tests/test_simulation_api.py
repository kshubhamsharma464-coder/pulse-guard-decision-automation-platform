"""Phase 4: simulation engine + bulk evaluation, exercised through the HTTP
API (in-memory backend, zero setup -- same convention as every other
router test in this project). RBAC follows tests/test_rule_management_api.py's
pattern: mutate the process-wide Settings singleton for auth_required,
restore in a fixture teardown.

decision_repository is a process-wide singleton shared by the ENTIRE test
session (every test module imports the same `app.main.app`), so tests here
never assert exact totals -- only deltas/presence for uniquely-generated
incident ids, same discipline the rest of the suite already follows."""

import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.settings import get_settings
from app.application.use_cases.register_user import RegisterUserUseCase
from app.application.use_cases.compare_rule_packs import CompareRulePacksUseCase
from app.application.use_cases.bulk_evaluate import BulkEvaluateUseCase
from app.domain.entities.incident import Incident
from app.interfaces.api.dependencies import (
    user_repository, role_repository, incident_repository, rule_repository, rule_pack_repository,
    decision_repository, evaluate_incident_use_case,
)

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


def _incident_payload(incident_id=None, **overrides):
    body = {
        "incidentId": incident_id or _unique("INC"),
        "towerId": "T-Delhi-101", "region": "Delhi", "affectedUsers": 15000,
        "vipCustomersAffected": True, "networkLoad": 94, "slaTier": "Gold",
        "maintenanceWindow": False, "weatherSeverity": "Moderate",
        "historicalFailures": 4, "incidentType": "Tower Down",
    }
    body.update(overrides)
    return body


def _low_severity_payload(incident_id=None, **overrides):
    body = {
        "incidentId": incident_id or _unique("INC-LOW"),
        "affectedUsers": 10, "networkLoad": 5, "vipCustomersAffected": False,
        "maintenanceWindow": False, "historicalFailures": 0, "incidentType": "Minor Glitch",
    }
    body.update(overrides)
    return body


def _aggressive_draft_pack(name=None):
    """A Draft rule pack (never activated) with one rule that always fires
    Critical -- used as a deliberately-different candidate for what-if/
    compare tests."""
    resp = client.post("/api/v1/rule-packs", json={
        "name": name or _unique("candidate-pack"),
        "rules": [{
            "ruleCode": "RSIM1", "name": "Always critical (test fixture)",
            "family": "NETWORK_IMPACT", "familyOrder": 1, "priorityWeight": 99,
            "conditions": {">=": [{"var": "affectedUsers"}, 0]},
            "actions": {"priority": "Critical", "notifyNOC": True},
        }],
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


# -- POST /api/v1/simulate (what-if) --------------------------------------

def test_what_if_against_active_pack_does_not_persist_anything():
    incident_id = _unique("INC-WHATIF")
    resp = client.post("/api/v1/simulate", json={"incident": _incident_payload(incident_id)})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["persisted"] is False
    assert body["rulePackUsed"]["source"] == "hot_path_active"
    assert body["decision"]["priority"] == "Critical"

    # Nothing was written -- no incident, no decision.
    assert client.get(f"/api/v1/incidents/{incident_id}").status_code == 404
    assert client.get(f"/api/v1/decisions/{incident_id}").status_code == 404


def test_what_if_against_explicit_draft_rule_pack():
    pack = _aggressive_draft_pack()
    resp = client.post("/api/v1/simulate", json={
        "incident": _low_severity_payload(), "rulePackId": pack["id"],
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rulePackUsed"] == {
        "source": "rule_pack", "id": pack["id"], "name": pack["name"],
        "version": pack["version"], "status": "draft", "region": None,
    }
    # The draft's single rule always fires Critical, regardless of the
    # incident being otherwise low-severity -- proves the candidate pack,
    # not the active one, was actually used.
    assert body["decision"]["priority"] == "Critical"


def test_what_if_unknown_rule_pack_id_returns_400():
    resp = client.post("/api/v1/simulate", json={"incident": _incident_payload(), "rulePackId": "no-such-id"})
    assert resp.status_code == 400


# -- POST /api/v1/simulate/replay -----------------------------------------

def test_replay_persisted_incident_against_same_active_pack_does_not_differ():
    incident_id = _unique("INC-REPLAY")
    create_resp = client.post("/api/v1/incidents", json=_incident_payload(incident_id))
    assert create_resp.status_code == 201, create_resp.text

    resp = client.post("/api/v1/simulate/replay", json={"incidentId": incident_id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["incidentId"] == incident_id
    assert body["originalDecision"] is not None
    assert body["differs"] is False
    assert body["differences"] == []
    assert body["replayedDecision"]["priority"] == body["originalDecision"]["priority"]


def test_replay_against_a_different_rule_pack_shows_a_difference():
    incident_id = _unique("INC-REPLAY-DIFF")
    create_resp = client.post("/api/v1/incidents", json=_low_severity_payload(incident_id))
    assert create_resp.status_code == 201, create_resp.text
    original_priority = create_resp.json()["decision"]["priority"]
    assert original_priority != "Critical"  # sanity: the low-severity payload isn't already Critical

    pack = _aggressive_draft_pack()
    resp = client.post("/api/v1/simulate/replay", json={"incidentId": incident_id, "rulePackId": pack["id"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["differs"] is True
    assert any("priority" in d for d in body["differences"])
    assert body["replayedDecision"]["priority"] == "Critical"


def test_replay_unknown_incident_returns_404():
    resp = client.post("/api/v1/simulate/replay", json={"incidentId": "no-such-incident"})
    assert resp.status_code == 404


# -- POST /api/v1/simulate/compare ----------------------------------------

def test_compare_baseline_vs_candidate_with_inline_incidents():
    pack = _aggressive_draft_pack()
    low = _low_severity_payload()
    resp = client.post("/api/v1/simulate/compare", json={
        "incidents": [low], "candidateRulePackId": pack["id"],
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["totalIncidents"] == 1
    assert body["differingCount"] == 1
    assert body["baseline"]["source"] == "hot_path_active"
    assert body["candidate"] == {
        "source": "rule_pack", "id": pack["id"], "name": pack["name"],
        "version": pack["version"], "status": "draft", "region": None,
    }
    diff = body["diffs"][0]
    assert diff["differs"] is True
    assert diff["candidatePriority"] == "Critical"


def test_compare_with_persisted_incident_ids():
    incident_id = _unique("INC-CMP")
    client.post("/api/v1/incidents", json=_low_severity_payload(incident_id))
    pack = _aggressive_draft_pack()

    resp = client.post("/api/v1/simulate/compare", json={
        "incidentIds": [incident_id], "candidateRulePackId": pack["id"],
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["diffs"][0]["incidentId"] == incident_id


def test_compare_requires_a_candidate_pack():
    resp = client.post("/api/v1/simulate/compare", json={"incidents": [_incident_payload()]})
    assert resp.status_code == 400


def test_compare_unknown_incident_id_returns_400():
    pack = _aggressive_draft_pack()
    resp = client.post("/api/v1/simulate/compare", json={
        "incidentIds": ["no-such-incident"], "candidateRulePackId": pack["id"],
    })
    assert resp.status_code == 400


def test_compare_use_case_enforces_max_incidents_cap():
    """HTTP-level cap enforcement is covered by the settings-driven
    Settings.simulation_max_compare_incidents wired into the real
    compare_rule_packs_use_case (dependencies.py); exercising the cap
    itself directly against the use case (small cap, real collaborators)
    is far cheaper than constructing 200+ HTTP payloads to hit the
    production default."""
    capped = CompareRulePacksUseCase(
        incident_repository, rule_repository, rule_pack_repository,
        orchestrator=evaluate_incident_use_case.orchestrator, max_incidents=1,
    )
    pack = _aggressive_draft_pack()
    incidents = [Incident(incident_id=_unique("INC-CAP"), payload={"affectedUsers": 1}) for _ in range(2)]
    with pytest.raises(ValueError, match="at most 1 incidents"):
        capped.execute(inline_incidents=incidents, candidate_pack_id=pack["id"])


# -- POST /api/v1/evaluate/bulk --------------------------------------------

def test_bulk_evaluate_persists_by_default_and_reports_distribution():
    ids = [_unique("INC-BULK") for _ in range(4)]
    incidents = [_incident_payload(i) for i in ids]
    resp = client.post("/api/v1/evaluate/bulk", json={"incidents": incidents})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["totalSubmitted"] == 4
    assert body["succeeded"] == 4
    assert body["failed"] == 0
    assert body["priorityDistribution"].get("Critical") == 4
    assert body["executionTimeMs"] >= 0
    assert len(body["results"]) == 4
    assert all(r["success"] and r["priority"] == "Critical" for r in body["results"])

    for incident_id in ids:
        assert client.get(f"/api/v1/decisions/{incident_id}").status_code == 200


def test_bulk_evaluate_dry_run_persists_nothing():
    ids = [_unique("INC-BULK-DRY") for _ in range(3)]
    incidents = [_incident_payload(i) for i in ids]
    resp = client.post("/api/v1/evaluate/bulk", json={"incidents": incidents, "persist": False})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["succeeded"] == 3

    for incident_id in ids:
        assert client.get(f"/api/v1/decisions/{incident_id}").status_code == 404


def test_bulk_evaluate_use_case_isolates_per_item_failures():
    """Failure isolation (one bad incident doesn't abort the batch) is
    exercised directly against BulkEvaluateUseCase with a fault-injecting
    fake use case, since a structurally-invalid HTTP payload (e.g. a
    missing incidentId) is instead caught by Pydantic before it ever
    reaches the use case -- that's a 422 on the whole request, a
    different and already-covered failure mode."""

    class _FlakyEvaluateUseCase:
        orchestrator = evaluate_incident_use_case.orchestrator

        def execute(self, incident, region=None, tenant=None):
            if incident.incident_id == "boom":
                raise RuntimeError("simulated evaluation failure")
            return evaluate_incident_use_case.execute(incident, region=region, tenant=tenant)

    flaky = _FlakyEvaluateUseCase()
    use_case = BulkEvaluateUseCase(persisting_use_case=flaky, dry_run_use_case=flaky, max_items=10)
    result = use_case.execute([
        {"incidentId": "boom", "affectedUsers": 1},
        {"incidentId": _unique("INC-OK"), "affectedUsers": 15000, "networkLoad": 94, "vipCustomersAffected": True},
    ])
    assert result.total == 2
    assert result.succeeded == 1
    assert result.failed == 1
    failed_entry = next(r for r in result.results if not r.success)
    assert failed_entry.incident_id == "boom"
    assert "simulated evaluation failure" in failed_entry.error


def test_bulk_evaluate_rejects_batches_over_the_configured_cap():
    small = BulkEvaluateUseCase(
        persisting_use_case=evaluate_incident_use_case, dry_run_use_case=evaluate_incident_use_case, max_items=2,
    )
    with pytest.raises(ValueError, match="at most 2 incidents"):
        small.execute([{"incidentId": f"x{i}"} for i in range(3)])


# -- GET /api/v1/decisions/distribution -------------------------------------

def test_decisions_distribution_reflects_newly_evaluated_incidents():
    before = client.get("/api/v1/decisions/distribution")
    assert before.status_code == 200
    before_total = before.json()["totalDecisions"]

    incident_id = _unique("INC-DIST")
    client.post("/api/v1/incidents/evaluate", json=_incident_payload(incident_id))

    after = client.get("/api/v1/decisions/distribution")
    assert after.status_code == 200
    after_body = after.json()
    assert after_body["totalDecisions"] == before_total + 1
    assert after_body["priorityDistribution"].get("Critical", 0) >= 1
    assert 0.0 <= after_body["averageConfidenceScore"] <= 100.0


def test_decisions_distribution_route_is_not_shadowed_by_incident_id_route():
    # GET /api/v1/decisions/distribution must resolve to the distribution
    # endpoint, not be swallowed by GET /api/v1/decisions/{incident_id}
    # treating "distribution" as a literal incident id.
    resp = client.get("/api/v1/decisions/distribution")
    assert resp.status_code == 200
    assert "totalDecisions" in resp.json()


# -- RBAC (auth_required=true only) -----------------------------------------

def test_viewer_cannot_run_simulations_or_bulk_evaluate(auth_required_on):
    viewer_headers = _bearer_for("viewer")
    resp = client.post("/api/v1/simulate", json={"incident": _incident_payload()}, headers=viewer_headers)
    assert resp.status_code == 403
    resp = client.post("/api/v1/evaluate/bulk", json={"incidents": [_incident_payload()]}, headers=viewer_headers)
    assert resp.status_code == 403


def test_editor_can_simulate_but_operator_is_needed_for_bulk_evaluate(auth_required_on):
    editor_headers = _bearer_for("editor")
    resp = client.post("/api/v1/simulate", json={"incident": _incident_payload()}, headers=editor_headers)
    assert resp.status_code == 200

    # editor has no incidents:evaluate permission -- bulk evaluate is denied.
    resp = client.post("/api/v1/evaluate/bulk", json={"incidents": [_incident_payload()]}, headers=editor_headers)
    assert resp.status_code == 403

    operator_headers = _bearer_for("operator")
    resp = client.post("/api/v1/evaluate/bulk", json={"incidents": [_incident_payload()]}, headers=operator_headers)
    assert resp.status_code == 200


def test_simulation_endpoints_open_by_default_when_auth_not_required():
    # No auth_required_on fixture -- confirms the untouched default
    # (auth_required=False) leaves every new Phase 4 endpoint open, same
    # backward-compatibility contract every earlier phase established.
    resp = client.post("/api/v1/simulate", json={"incident": _incident_payload()})
    assert resp.status_code == 200
