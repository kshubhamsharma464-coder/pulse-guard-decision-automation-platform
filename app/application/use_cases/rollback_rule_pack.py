import uuid
from datetime import datetime, timezone
from typing import Optional
from app.domain.entities.rule_pack import RulePack
from app.domain.entities.audit_log_entry import AuditLogEntry
from app.domain.exceptions import ConcurrentModificationError
from app.domain.interfaces.rule_pack_repository import RulePackRepository
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.interfaces.cache_refresh_notifier import CacheRefreshNotifier, CacheRefreshEvent


class RollbackRulePackUseCase:
    """Design doc §9 edge case #11: rollback is a single write to the prior
    version via parent_version, not a redeploy.

    cache/notifier/audit_log_repository (added for the dynamic Rule
    Management platform, docs/rule-management.md) are optional and default
    to None -- constructing this with just a repository, and calling
    execute(name, current_version) with no extra kwargs, behaves exactly
    as it did before this file was extended (see
    tests/test_rule_pack_lifecycle.py, unmodified)."""

    def __init__(
        self, repository: RulePackRepository, cache=None,
        notifier: Optional[CacheRefreshNotifier] = None,
        audit_log_repository: Optional[AuditLogRepository] = None,
    ):
        self.repository = repository
        self.cache = cache
        self.notifier = notifier
        self.audit_log_repository = audit_log_repository

    def execute(
        self, name: str, current_version: int, actor: str = "system",
        reason: Optional[str] = None, correlation_id: Optional[str] = None,
        expected_lock_version: Optional[int] = None,
    ) -> RulePack:
        current = self.repository.get(name, current_version)
        if current is None:
            raise ValueError(f"No such rule pack version: {name} v{current_version}")
        if current.parent_version is None:
            raise ValueError(f"{name} v{current_version} has no parent version to roll back to")
        # Phase 5 (docs/policy-platform.md): checked against `current` (the
        # version being rolled back FROM, i.e. what the caller actually
        # read before deciding to roll back) -- NOT passed to activate()
        # below, which would incorrectly apply it to the PARENT row being
        # activated instead of the row this check is actually about.
        if expected_lock_version is not None and current.lock_version != expected_lock_version:
            raise ConcurrentModificationError(
                f"{name} v{current_version} was modified by someone else since it was loaded "
                f"(expected lock_version={expected_lock_version}, current={current.lock_version}) -- "
                "reload the latest state and retry the rollback."
            )

        rolled_back = self.repository.activate(name, current.parent_version)

        if self.notifier is not None:
            self.notifier.publish(CacheRefreshEvent(entity_type="rule_pack", entity_id=rolled_back.id, action="rolled_back"))
        if self.audit_log_repository is not None:
            self.audit_log_repository.save(AuditLogEntry(
                id=str(uuid.uuid4()), entity_type="rule_pack", entity_id=rolled_back.id or f"{name}", action="rolled_back",
                actor=actor,
                before={"name": name, "version": current_version, "status": current.status},
                after={"name": name, "version": rolled_back.version, "status": rolled_back.status},
                ip_address=None, request_id=None, correlation_id=correlation_id,
                created_at=datetime.now(timezone.utc), reason=reason,
            ))
        return rolled_back
