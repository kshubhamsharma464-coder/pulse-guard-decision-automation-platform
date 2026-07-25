from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_openapi_json_is_served_and_well_formed():
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["info"]["title"] == "Pulse Guard"

    expected_paths = {
        "/api/v1/incidents/evaluate",
        "/api/v1/decisions/{incident_id}",
        "/api/v1/decisions/{incident_id}/history",
        "/health",
    }
    assert expected_paths.issubset(spec["paths"].keys())

    schemas = spec["components"]["schemas"]
    assert "IncidentEvaluateRequest" in schemas
    assert "DecisionResponse" in schemas
    assert "example" in schemas["IncidentEvaluateRequest"]


def test_swagger_ui_is_served():
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "swagger" in resp.text.lower()


def test_openapi_exposes_bearer_auth_only():
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    security_schemes = spec.get("components", {}).get("securitySchemes", {})
    assert "bearerAuth" in security_schemes
    assert "apiKey" not in security_schemes
