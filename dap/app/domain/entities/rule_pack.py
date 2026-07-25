from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from app.domain.entities.rule import Rule

# Lifecycle states supported by the dynamic Rule Management platform
# (docs/rule-management.md). The original design doc's vocabulary
# (draft/validated/shadow/active/deprecated/rolled_back) predates this and
# still works as arbitrary strings on `status` -- these constants are the
# ones the new /api/v1/rule-packs endpoints actually use and validate
# transitions against (see RulePackStatus.can_transition below).
DRAFT = "draft"
PUBLISHED = "published"
ACTIVE = "active"
DEPRECATED = "deprecated"
ARCHIVED = "archived"

_ALLOWED_TRANSITIONS = {
    DRAFT: {PUBLISHED, ARCHIVED},
    PUBLISHED: {ACTIVE, ARCHIVED, DRAFT},  # DRAFT: publishing can be reverted before activation
    ACTIVE: {DEPRECATED, ARCHIVED},
    DEPRECATED: {ACTIVE, ARCHIVED},        # re-activating a deprecated version IS how rollback works
    ARCHIVED: set(),                        # terminal -- archived (soft-deleted) packs can't transition further
}


def can_transition(current: str, target: str) -> bool:
    return target in _ALLOWED_TRANSITIONS.get(current, set())


@dataclass
class RulePack:
    name: str
    version: int
    status: str
    region: Optional[str]
    rules: List[Rule] = field(default_factory=list)
    parent_version: Optional[int] = None  # design doc §9 edge case #11: rollback target

    # Added for the dynamic Rule Management platform (docs/rule-management.md)
    # -- all optional/defaulted so every pre-existing construction of
    # RulePack() across the codebase and test suite is unaffected.
    id: Optional[str] = None
    tenant_id: Optional[str] = None
    created_by: str = "system"
    created_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    # Phase 5 (docs/policy-platform.md, "Concurrency") -- optimistic
    # concurrency token, surfaced to API clients as `lockVersion`. A
    # caller that read this pack at lock_version=N and wants to mutate it
    # passes `expectedLockVersion=N` back on the write; the repository
    # rejects the write with ConcurrentModificationError if the row's
    # current lock_version has since moved past N (someone else's write
    # landed in between). Defaulted to 1 (matching OptimisticLockMixin's
    # own default) so every pre-existing RulePack() construction is
    # unaffected.
    lock_version: int = 1

    def active_rules(self, family: Optional[str] = None) -> List[Rule]:
        rules = [r for r in self.rules if r.is_active()]
        if family is not None:
            rules = [r for r in rules if r.family == family]
        return sorted(rules, key=lambda r: (r.family_order, -r.priority_weight))
