"""End-to-end proof that Settings.rule_source="dynamic" actually makes
POST /api/v1/incidents/evaluate read from a rule pack created/published/
activated through the new /api/v1/rule-packs and /api/v1/rules HTTP API --
with zero application restart between activating a pack and the next
evaluation seeing it.

Runs in a genuinely separate Python process (subprocess), not just a
different test function, because Settings is an lru_cache'd singleton
read once at import time by app/interfaces/api/dependencies.py -- toggling
env vars inside the same already-imported test process wouldn't change
what dependencies.py already wired up. A fresh interpreter with
PERSISTENCE_BACKEND=postgres, RULE_SOURCE=dynamic, and a throwaway SQLite
file standing in for Postgres (same substitution methodology as
tests/test_postgres_repositories.py) is the only way to exercise this
for real."""

import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

_SCRIPT = textwrap.dedent("""
    import sys
    sys.path.insert(0, ".")
    from app.infrastructure.db.base import Base
    from app.infrastructure.db import models
    from sqlalchemy import create_engine
    engine = create_engine("{db_url}")
    Base.metadata.create_all(engine)

    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)

    pack = client.post("/api/v1/rule-packs", json={{"name": "noc-default"}}).json()
    client.post(f"/api/v1/rules?rulePackId={{pack['id']}}", json={{
        "ruleCode": "DYNTEST", "name": "dyn", "conditions": {{"==": [{{"var": "x"}}, 1]}},
        "actions": {{"priority": "Critical"}},
    }})
    client.post(f"/api/v1/rule-packs/{{pack['id']}}/publish")
    client.post(f"/api/v1/rule-packs/{{pack['id']}}/activate")

    resp = client.post("/api/v1/incidents/evaluate", json={{"incidentId": "INC-1", "x": 1}})
    assert resp.status_code == 200, resp.text
    matched = [r["rule_code"] for r in resp.json()["matchedRules"]]
    assert matched == ["DYNTEST"], f"expected only DYNTEST to match, got {{matched}}"
    print("DYNAMIC_SOURCE_OK")
""")


def test_dynamic_rule_source_serves_live_activated_pack():
    project_root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "dynamic_test.db"
        db_url = f"sqlite:///{db_path.as_posix()}"
        script = _SCRIPT.format(db_url=db_url)
        env = dict(os.environ)
        env.update({
            "PERSISTENCE_BACKEND": "postgres",
            "RULE_SOURCE": "dynamic",
            "DATABASE_URL": db_url,
        })
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(project_root),
            env=env,
            capture_output=True, text=True, timeout=60,
        )
        assert "DYNAMIC_SOURCE_OK" in result.stdout, f"stdout={result.stdout}\nstderr={result.stderr}"
