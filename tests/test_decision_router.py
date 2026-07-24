from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_evaluate_then_retrieve_by_incident_id(inc_101_payload):
    post_resp = client.post("/api/v1/incidents/evaluate", json=inc_101_payload)
    assert post_resp.status_code == 200

    get_resp = client.get(f"/api/v1/decisions/{inc_101_payload['incidentId']}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["priority"] == "Critical"
    assert body["incidentId"] == inc_101_payload["incidentId"]


def test_history_grows_across_repeated_evaluations(inc_101_payload):
    payload = dict(inc_101_payload)
    payload["incidentId"] = "INC-HISTORY-TEST"
    client.post("/api/v1/incidents/evaluate", json=payload)
    client.post("/api/v1/incidents/evaluate", json=payload)

    history_resp = client.get("/api/v1/decisions/INC-HISTORY-TEST/history")
    assert history_resp.status_code == 200
    assert len(history_resp.json()) == 2


def test_unknown_incident_returns_404():
    resp = client.get("/api/v1/decisions/DOES-NOT-EXIST")
    assert resp.status_code == 404
