"""Postgres-backed RulePackRepository -- full lifecycle (save/get/
get_active/list_versions/activate), same contract as
InMemoryRulePackRepository (including "exactly one active version per
name+region" and push-cache-invalidation on activate()).

Phase 5 (docs/policy-platform.md, "Concurrency"): every method that
commits a change to an existing row goes through self._commit(session),
which catches SQLAlchemy's StaleDataError (raised by RuleSetORM's now-real
version_id_col -- see models.py's docstring on that class) and re-raises
it as the framework-independent ConcurrentModificationError. Two
concurrent writers loading the same rule-pack version and both trying to
commit a change based on it is exactly the "100+ business users editing
rules... no dirty reads" scenario the enterprise requirements call out --
this is what makes the second writer's commit fail loudly and cleanly
(409 Conflict at the API layer, see main.py's exception handler) instead
of silently overwriting the first writer's change."""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import sessionmaker, joinedload, Session
from sqlalchemy.orm.exc import StaleDataError
from app.domain.interfaces.rule_pack_repository import RulePackRepository
from app.domain.entities.rule_pack import RulePack, ARCHIVED
from app.domain.exceptions import ConcurrentModificationError
from app.infrastructure.db.models import RuleSetORM
from app.infrastructure.db.mappers import rule_to_domain, rule_to_orm
from app.core.cache import TTLCache


class PostgresRulePackRepository(RulePackRepository):
    def __init__(self, session_factory: sessionmaker, active_pack_cache: Optional[TTLCache] = None):
        self._session_factory = session_factory
        self._active_pack_cache = active_pack_cache or TTLCache(ttl_seconds=10.0)

    @staticmethod
    def _commit(session: Session) -> None:
        try:
            session.commit()
        except StaleDataError as exc:
            session.rollback()
            raise ConcurrentModificationError(
                "This rule pack was modified by someone else since it was loaded -- reload the "
                "latest version and retry your change."
            ) from exc

    def save(self, pack: RulePack) -> RulePack:
        with self._session_factory() as session:
            existing = (
                session.query(RuleSetORM)
                .filter(RuleSetORM.name == pack.name, RuleSetORM.version == pack.version)
                .first()
            )
            if existing is not None:
                existing.status = pack.status
                existing.region = pack.region
                existing.created_by = pack.created_by
                row = existing
                row.rules.clear()
            else:
                row = RuleSetORM(
                    name=pack.name, version=pack.version, status=pack.status, region=pack.region,
                    created_by=pack.created_by,
                )
                if pack.parent_version is not None:
                    parent = (
                        session.query(RuleSetORM)
                        .filter(RuleSetORM.name == pack.name, RuleSetORM.version == pack.parent_version)
                        .first()
                    )
                    if parent is not None:
                        row.parent_version_id = parent.id
                session.add(row)
                session.flush()  # assign row.id before attaching child rules

            for rule in pack.rules:
                row.rules.append(rule_to_orm(rule, row.id))

            self._commit(session)
            session.refresh(row)
            pack.id = str(row.id)
            pack.created_at = row.created_at
            return pack

    def get(self, name: str, version: int) -> Optional[RulePack]:
        with self._session_factory() as session:
            row = (
                session.query(RuleSetORM)
                .options(joinedload(RuleSetORM.rules))
                .filter(RuleSetORM.name == name, RuleSetORM.version == version)
                .first()
            )
            return self._to_domain(row, session) if row else None

    def get_by_id(self, pack_id: str) -> Optional[RulePack]:
        with self._session_factory() as session:
            row = (
                session.query(RuleSetORM)
                .options(joinedload(RuleSetORM.rules))
                .filter(RuleSetORM.id == pack_id, RuleSetORM.status != ARCHIVED)
                .first()
            )
            return self._to_domain(row, session) if row else None

    def list_all(
        self, status: Optional[str] = None, region: Optional[str] = None,
        include_archived: bool = False, limit: int = 50, offset: int = 0,
    ) -> List[RulePack]:
        with self._session_factory() as session:
            query = session.query(RuleSetORM).options(joinedload(RuleSetORM.rules))
            if not include_archived:
                query = query.filter(RuleSetORM.status != ARCHIVED)
            if status is not None:
                query = query.filter(RuleSetORM.status == status)
            if region is not None:
                query = query.filter(RuleSetORM.region == region)
            rows = query.order_by(RuleSetORM.name, RuleSetORM.version).offset(offset).limit(limit).all()
            return [self._to_domain(r, session) for r in rows]

    @staticmethod
    def _check_lock(row: RuleSetORM, expected_lock_version: Optional[int]) -> None:
        """Phase 5 optimistic-concurrency check -- see RulePackRepository's
        docstring. Deliberately a check against `row.lock_version` as read
        FRESH at the top of this method (not whatever the caller's own
        stale copy might say), which is what actually catches "someone
        else already changed this since you last read it": if fields[key]
        differs from what the caller expected, someone else's write
        landed in between the caller's GET and this PATCH."""
        if expected_lock_version is not None and row.lock_version != expected_lock_version:
            raise ConcurrentModificationError(
                f"Rule pack {row.id} was modified by someone else since it was loaded "
                f"(expected lock_version={expected_lock_version}, current={row.lock_version}) -- "
                "reload the latest version and retry your change."
            )

    def update_metadata(self, pack_id: str, expected_lock_version: Optional[int] = None, **fields) -> RulePack:
        with self._session_factory() as session:
            row = session.get(RuleSetORM, pack_id)
            if row is None:
                raise ValueError(f"No such rule pack: {pack_id}")
            self._check_lock(row, expected_lock_version)
            for key in ("name", "region", "tenant_id", "created_by"):
                if key in fields and fields[key] is not None:
                    setattr(row, key, fields[key])
            self._commit(session)
            session.refresh(row)
            return self._to_domain(row, session)

    def update_status(self, pack_id: str, status: str, expected_lock_version: Optional[int] = None) -> RulePack:
        with self._session_factory() as session:
            row = session.get(RuleSetORM, pack_id)
            if row is None:
                raise ValueError(f"No such rule pack: {pack_id}")
            self._check_lock(row, expected_lock_version)
            row.status = status
            self._commit(session)
            session.refresh(row)
            return self._to_domain(row, session)

    def soft_delete(self, pack_id: str, expected_lock_version: Optional[int] = None) -> RulePack:
        with self._session_factory() as session:
            row = session.get(RuleSetORM, pack_id)
            if row is None:
                raise ValueError(f"No such rule pack: {pack_id}")
            self._check_lock(row, expected_lock_version)
            row.status = ARCHIVED
            row.deleted_at = datetime.now(timezone.utc)
            self._commit(session)
            session.refresh(row)
            self._active_pack_cache.invalidate()
            return self._to_domain(row, session)

    def get_active(self, name: str, region: Optional[str] = None) -> Optional[RulePack]:
        with self._session_factory() as session:
            row = (
                session.query(RuleSetORM)
                .options(joinedload(RuleSetORM.rules))
                .filter(RuleSetORM.name == name, RuleSetORM.status == "active", RuleSetORM.region == region)
                .first()
            )
            return self._to_domain(row, session) if row else None

    def list_versions(self, name: str) -> List[RulePack]:
        with self._session_factory() as session:
            rows = (
                session.query(RuleSetORM)
                .options(joinedload(RuleSetORM.rules))
                .filter(RuleSetORM.name == name)
                .order_by(RuleSetORM.version)
                .all()
            )
            return [self._to_domain(r, session) for r in rows]

    def activate(self, name: str, version: int, expected_lock_version: Optional[int] = None) -> RulePack:
        with self._session_factory() as session:
            target = (
                session.query(RuleSetORM)
                .options(joinedload(RuleSetORM.rules))
                .filter(RuleSetORM.name == name, RuleSetORM.version == version)
                .first()
            )
            if target is None:
                raise ValueError(f"No such rule pack version: {name} v{version}")
            self._check_lock(target, expected_lock_version)

            currently_active = (
                session.query(RuleSetORM)
                .filter(RuleSetORM.name == name, RuleSetORM.status == "active")
                .all()
            )
            for row in currently_active:
                row.status = "deprecated"
            target.status = "active"
            target.activated_at = datetime.now(timezone.utc)
            self._commit(session)
            session.refresh(target)

            self._active_pack_cache.invalidate()
            return self._to_domain(target, session)

    @staticmethod
    def _resolve_parent_version(session: Session, parent_version_id) -> Optional[int]:
        """parent_version_id is a UUID FK to another rule_sets row;
        RulePack.parent_version stores that row's integer `version` field,
        not its UUID -- resolved here since only the repository has a
        session to look it up with."""
        if parent_version_id is None:
            return None
        parent = session.get(RuleSetORM, parent_version_id)
        return parent.version if parent is not None else None

    def _to_domain(self, row: RuleSetORM, session: Session) -> RulePack:
        return RulePack(
            id=str(row.id),
            name=row.name,
            version=row.version,
            status=row.status,
            region=row.region,
            rules=[rule_to_domain(r) for r in row.rules],
            parent_version=self._resolve_parent_version(session, row.parent_version_id),
            tenant_id=str(row.tenant_id) if row.tenant_id else None,
            created_by=row.created_by,
            created_at=row.created_at,
            activated_at=row.activated_at,
            deleted_at=row.deleted_at,
            lock_version=row.lock_version,
        )
