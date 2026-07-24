"""Phase 2: security headers (always-on) and rate limiting (opt-in)."""

from fastapi.testclient import TestClient
from app.main import app
from app.core.settings import get_settings

client = TestClient(app)


def test_security_headers_present_on_every_response():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "no-referrer"


def test_rate_limiting_disabled_by_default_allows_many_requests():
    for _ in range(20):
        resp = client.get("/health")
        assert resp.status_code == 200


def test_rate_limiting_enforced_when_enabled():
    settings = get_settings()
    original_enabled = settings.rate_limit_enabled
    original_limit = settings.rate_limit_requests_per_minute
    settings.rate_limit_enabled = True
    settings.rate_limit_requests_per_minute = 3
    try:
        statuses = [client.get("/health").status_code for _ in range(6)]
        assert statuses.count(429) > 0, f"expected at least one 429, got {statuses}"
        assert 429 in statuses[3:]  # the limit should bite after the 3rd request in-window
    finally:
        settings.rate_limit_enabled = original_enabled
        settings.rate_limit_requests_per_minute = original_limit
