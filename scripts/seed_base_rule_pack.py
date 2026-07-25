"""One-time seed: load rules-seed.json's 35-rule base pack into Postgres
via PostgresRulePackRepository, then activate it. Lets rule-pack lifecycle
features (versioning, rollback, compare) be exercised against real data.

NOTE: this does NOT make the hot incident-evaluation path read from
Postgres -- that still uses the in-memory CompositeRuleRepository merging
all 7 rule packs (see dependencies.py's module docstring for why that's a
deliberate, separate scope boundary). This seed is for the rule-pack
lifecycle/admin side only.

Run after `alembic upgrade head`:

    python3 scripts/seed_base_rule_pack.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.settings import get_settings
from app.infrastructure.db.session import get_engine, get_sessionmaker
from app.infrastructure.repositories.in_memory_rule_repository import InMemoryRuleRepository
from app.infrastructure.repositories.postgres_rule_pack_repository import PostgresRulePackRepository


def main() -> None:
    settings = get_settings()
    engine = get_engine(settings.database_url)
    session_factory = get_sessionmaker(engine)

    pack = InMemoryRuleRepository().get_active()
    repo = PostgresRulePackRepository(session_factory)

    if repo.get(pack.name, pack.version) is not None:
        print(f"{pack.name} v{pack.version} already seeded -- skipping save")
    else:
        repo.save(pack)
        print(f"seeded {pack.name} v{pack.version} ({len(pack.rules)} rules)")

    repo.activate(pack.name, pack.version)
    print(f"activated {pack.name} v{pack.version}")


if __name__ == "__main__":
    main()
