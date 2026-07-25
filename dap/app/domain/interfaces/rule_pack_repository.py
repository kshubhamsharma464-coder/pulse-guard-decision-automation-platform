from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.entities.rule_pack import RulePack


class RulePackRepository(ABC):
    """Lifecycle-aware repository -- draft/validate/shadow/activate/rollback.
    Distinct from RuleRepository, which only exposes get_active() for the
    evaluation hot path (design doc §8).

    get_by_id/list_all/update_metadata/soft_delete (added for the dynamic
    Rule Management platform, docs/rule-management.md) are the CRUD surface
    the /api/v1/rule-packs/* endpoints call directly; save/get/get_active/
    list_versions/activate remain the original lifecycle primitives.

    Every mutating method below (update_metadata/update_status/soft_delete/
    activate) accepts an optional `expected_lock_version` (Phase 5,
    docs/policy-platform.md's "Concurrency" section) -- when given, the
    implementation must raise app.domain.exceptions.ConcurrentModificationError
    if the pack's CURRENT lock_version doesn't match, before making any
    change. `None` (the default) skips the check entirely -- every
    pre-existing call site that never passes this keeps working exactly
    as before Phase 5. This is real optimistic concurrency (an ETag-style
    read-then-conditional-write), not just a version counter that
    increments unobserved: a client must have actually read the pack (and
    therefore its lock_version) before it can meaningfully assert what it
    expected, which is why this is a caller-supplied value, not something
    a repository could infer on its own."""

    @abstractmethod
    def save(self, pack: RulePack) -> RulePack: ...

    @abstractmethod
    def get(self, name: str, version: int) -> Optional[RulePack]: ...

    @abstractmethod
    def get_by_id(self, pack_id: str) -> Optional[RulePack]: ...

    @abstractmethod
    def get_active(self, name: str, region: Optional[str] = None) -> Optional[RulePack]: ...

    @abstractmethod
    def list_versions(self, name: str) -> List[RulePack]: ...

    @abstractmethod
    def list_all(
        self, status: Optional[str] = None, region: Optional[str] = None,
        include_archived: bool = False, limit: int = 50, offset: int = 0,
    ) -> List[RulePack]: ...

    @abstractmethod
    def update_metadata(self, pack_id: str, expected_lock_version: Optional[int] = None, **fields) -> RulePack: ...

    @abstractmethod
    def update_status(self, pack_id: str, status: str, expected_lock_version: Optional[int] = None) -> RulePack:
        """A plain status write with no side effects (no cache invalidation,
        no cascading deprecation of a prior active row) -- that's what
        activate() is for. This is for simple transitions like Draft ->
        Published that don't touch what's currently serving traffic."""
        ...

    @abstractmethod
    def soft_delete(self, pack_id: str, expected_lock_version: Optional[int] = None) -> RulePack: ...

    @abstractmethod
    def activate(self, name: str, version: int, expected_lock_version: Optional[int] = None) -> RulePack: ...
