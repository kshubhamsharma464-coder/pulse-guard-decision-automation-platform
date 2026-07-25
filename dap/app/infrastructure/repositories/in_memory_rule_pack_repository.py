import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from app.domain.interfaces.rule_pack_repository import RulePackRepository
from app.domain.entities.rule_pack import RulePack, ARCHIVED
from app.domain.exceptions import ConcurrentModificationError
from app.core.cache import TTLCache


class InMemoryRulePackRepository(RulePackRepository):
    """In-memory stand-in for the rule_sets table's lifecycle operations. A
    PostgresRulePackRepository replaces this behind the same interface once
    infrastructure/database is wired up -- nothing above this layer changes.

    NOTE: kept deliberately separate from InMemoryRuleRepository (used by the
    hot evaluation path) rather than refactored together, so the already-
    tested evaluation path wasn't put at risk while adding lifecycle
    management. A real Postgres implementation backs both from the same
    rule_sets/rules tables."""

    def __init__(self, active_pack_cache: TTLCache = None):
        self._store: Dict[Tuple[str, int], RulePack] = {}
        # Push-invalidated on activate() below; TTL is only the fallback
        # safety net (tradeoffs.md #17 -- the cache-invalidation decision).
        self._active_pack_cache = active_pack_cache or TTLCache(ttl_seconds=10.0)

    def save(self, pack: RulePack) -> RulePack:
        if pack.id is None:
            pack.id = str(uuid.uuid4())
        if pack.created_at is None:
            pack.created_at = datetime.now(timezone.utc)
        self._store[(pack.name, pack.version)] = pack
        return pack

    def get(self, name: str, version: int) -> Optional[RulePack]:
        return self._store.get((name, version))

    def get_by_id(self, pack_id: str) -> Optional[RulePack]:
        for pack in self._store.values():
            if pack.id == pack_id:
                return pack
        return None

    def get_active(self, name: str, region: Optional[str] = None) -> Optional[RulePack]:
        for pack in self._store.values():
            if pack.name == name and pack.status == "active" and pack.region == region:
                return pack
        return None

    def list_versions(self, name: str) -> List[RulePack]:
        return sorted((p for p in self._store.values() if p.name == name), key=lambda p: p.version)

    def list_all(
        self, status: Optional[str] = None, region: Optional[str] = None,
        include_archived: bool = False, limit: int = 50, offset: int = 0,
    ) -> List[RulePack]:
        packs = list(self._store.values())
        if not include_archived:
            packs = [p for p in packs if p.status != ARCHIVED]
        if status is not None:
            packs = [p for p in packs if p.status == status]
        if region is not None:
            packs = [p for p in packs if p.region == region]
        packs.sort(key=lambda p: (p.name, p.version))
        return packs[offset: offset + limit]

    @staticmethod
    def _check_lock(pack: RulePack, expected_lock_version: Optional[int]) -> None:
        """Phase 5 optimistic-concurrency check -- see RulePackRepository's
        docstring. Mirrors PostgresRulePackRepository's check so both
        backends enforce the identical contract regardless of
        Settings.persistence_backend."""
        if expected_lock_version is not None and pack.lock_version != expected_lock_version:
            raise ConcurrentModificationError(
                f"Rule pack {pack.id} was modified by someone else since it was loaded "
                f"(expected lock_version={expected_lock_version}, current={pack.lock_version}) -- "
                "reload the latest version and retry your change."
            )

    def update_metadata(self, pack_id: str, expected_lock_version: Optional[int] = None, **fields) -> RulePack:
        pack = self.get_by_id(pack_id)
        if pack is None:
            raise ValueError(f"No such rule pack: {pack_id}")
        self._check_lock(pack, expected_lock_version)
        for key, value in fields.items():
            if hasattr(pack, key):
                setattr(pack, key, value)
        pack.lock_version += 1
        return pack

    def update_status(self, pack_id: str, status: str, expected_lock_version: Optional[int] = None) -> RulePack:
        pack = self.get_by_id(pack_id)
        if pack is None:
            raise ValueError(f"No such rule pack: {pack_id}")
        self._check_lock(pack, expected_lock_version)
        pack.status = status
        pack.lock_version += 1
        return pack

    def soft_delete(self, pack_id: str, expected_lock_version: Optional[int] = None) -> RulePack:
        pack = self.get_by_id(pack_id)
        if pack is None:
            raise ValueError(f"No such rule pack: {pack_id}")
        self._check_lock(pack, expected_lock_version)
        pack.status = ARCHIVED
        pack.deleted_at = datetime.now(timezone.utc)
        pack.lock_version += 1
        self._active_pack_cache.invalidate()
        return pack

    def activate(self, name: str, version: int, expected_lock_version: Optional[int] = None) -> RulePack:
        target = self.get(name, version)
        if target is None:
            raise ValueError(f"No such rule pack version: {name} v{version}")
        self._check_lock(target, expected_lock_version)
        for pack in self.list_versions(name):
            if pack.status == "active":
                pack.status = "deprecated"
                pack.lock_version += 1
        target.status = "active"
        target.activated_at = datetime.now(timezone.utc)
        target.lock_version += 1
        # Push invalidation immediately -- in a multi-replica deployment this
        # fires over Postgres LISTEN/NOTIFY so every replica invalidates now,
        # not after its next TTL expiry.
        self._active_pack_cache.invalidate()
        return target
