"""Postgres-backed RuleRepository -- same interface as
InMemoryRuleRepository/CompositeRuleRepository, selected via
Settings.rule_source == "dynamic" (see dependencies.py). This IS the
"ActiveRulePackProvider"/"CachedProvider" the Rule Management platform
spec asks for -- RuleRepository.get_active() already has exactly that
shape, so rather than invent a parallel interface, this class fulfills it
directly (docs/rule-management.md explains that choice).

Optionally wraps a RuleCache (app/infrastructure/cache/rule_cache.py): if
one is supplied, get_active() reads through it instead of hitting Postgres
on every call -- the cache self-invalidates via CacheRefreshNotifier
whenever a rule-pack mutation (publish/activate/rollback/delete) is
published, so this never serves data older than the last committed
change plus at most one in-flight read."""

from typing import Optional
from sqlalchemy.orm import sessionmaker, joinedload
from app.domain.interfaces.rule_repository import RuleRepository
from app.domain.entities.rule_pack import RulePack
from app.infrastructure.db.models import RuleSetORM
from app.infrastructure.db.mappers import rule_to_domain


class PostgresRuleRepository(RuleRepository):
    def __init__(self, session_factory: sessionmaker, rule_set_name: str = "noc-default", cache=None):
        self._session_factory = session_factory
        self._rule_set_name = rule_set_name
        self._cache = cache  # Optional[RuleCache] -- kept untyped here to avoid a hard import cycle

    def get_active(self, region: Optional[str] = None, tenant: Optional[str] = None) -> RulePack:
        loader = lambda: self._load_from_db(region, tenant)
        if self._cache is not None:
            return self._cache.get(loader)
        return loader()

    def load_from_source(self, region: Optional[str] = None, tenant: Optional[str] = None) -> RulePack:
        """Public alias for _load_from_db -- bypasses the cache entirely,
        always reading PostgreSQL directly. Exists specifically for the
        composition root (dependencies.py) to hand RuleCache.bind_loader()
        a callable that can't recurse back into get_active() (which reads
        through the very cache being bound)."""
        return self._load_from_db(region, tenant)

    def _load_from_db(self, region: Optional[str], tenant: Optional[str]) -> RulePack:
        with self._session_factory() as session:
            row = (
                session.query(RuleSetORM)
                .options(joinedload(RuleSetORM.rules))
                .filter(
                    RuleSetORM.name == self._rule_set_name,
                    RuleSetORM.status == "active",
                    RuleSetORM.region == region,
                    RuleSetORM.deleted_at.is_(None),
                )
                .first()
            )
            if row is None:
                raise LookupError(
                    f"No active rule set named '{self._rule_set_name}' for region={region!r}. "
                    "Run scripts/seed_base_rule_pack.py, or create+publish+activate one via "
                    "POST /api/v1/rule-packs, after migrating."
                )
            parent_version = None
            if row.parent_version_id is not None:
                parent = session.get(RuleSetORM, row.parent_version_id)
                parent_version = parent.version if parent is not None else None
            return RulePack(
                id=str(row.id),
                name=row.name,
                version=row.version,
                status=row.status,
                region=row.region,
                rules=[rule_to_domain(r) for r in row.rules],
                parent_version=parent_version,
                tenant_id=str(row.tenant_id) if row.tenant_id else None,
                created_by=row.created_by,
                created_at=row.created_at,
                activated_at=row.activated_at,
            )
