"""One-time seed: populate escalation_policies with the same default
tiers InMemoryEscalationPolicyRepository ships with (see its own
docstring/module for the reasoning behind the timings). Run after
`alembic upgrade head`:

    python3 scripts/seed_escalation_policies.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.settings import get_settings
from app.infrastructure.db.session import get_engine, get_sessionmaker
from app.infrastructure.repositories.in_memory_escalation_policy_repository import _DEFAULT_POLICIES
from app.infrastructure.db.mappers import escalation_policy_to_orm
from app.infrastructure.db.models import EscalationPolicyORM


def main() -> None:
    settings = get_settings()
    engine = get_engine(settings.database_url)
    session_factory = get_sessionmaker(engine)

    with session_factory() as session:
        existing = {row.severity_band for row in session.query(EscalationPolicyORM).all()}
        added = 0
        for band, policy in _DEFAULT_POLICIES.items():
            if band in existing:
                print(f"  skip {band} (already seeded)")
                continue
            session.add(escalation_policy_to_orm(policy))
            added += 1
            print(f"  seeded {band}: {[(l.level, l.timeout_minutes) for l in policy.levels]}")
        session.commit()
    print(f"done -- {added} policy row(s) added")


if __name__ == "__main__":
    main()
