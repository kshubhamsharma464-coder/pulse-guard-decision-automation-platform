#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${DATABASE_URL:-}" ]]; then
  echo "Waiting for database to become available..."
  until python - <<'PY'
import os
from sqlalchemy import create_engine

url = os.environ["DATABASE_URL"]
engine = create_engine(url)
try:
    with engine.connect():
        pass
except Exception as exc:
    raise SystemExit(str(exc))
PY
  do
    sleep 2
  done
fi

if command -v alembic >/dev/null 2>&1; then
  echo "Applying database migrations..."
  alembic upgrade head
else
  echo "Warning: alembic not found; skipping migrations."
fi

echo "Seeding defaults..."
python scripts/seed_default_roles_permissions.py
python scripts/seed_escalation_policies.py
python scripts/seed_base_rule_pack.py

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"