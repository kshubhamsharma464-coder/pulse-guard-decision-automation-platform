from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_evaluate_inc_101_end_to_end(inc_101_payload):
    resp = client.post("/api/v1/incidents/evaluate", json=inc_101_payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["priority"] == "Critical"
    matched_codes = {r["rule_code"] for r in body["matchedRules"]}
    assert {"R001", "R004", "R007"}.issubset(matched_codes)
    assert body["decision"]["targetSLA"] == "15 minutes"
    assert "explanation" in body and len(body["explanation"]) > 0
