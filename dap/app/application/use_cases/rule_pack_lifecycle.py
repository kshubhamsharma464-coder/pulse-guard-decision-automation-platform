"""Rule pack lifecycle use cases for the dynamic Rule Management platform
(docs/rule-management.md): create draft, import/export JSON, update
metadata, soft delete, publish, activate. Complements the pre-existing
ValidateRulePackUseCase/RollbackRulePackUseCase (unchanged, still used
directly).

Every mutating use case here takes optional `cache`/`notifier`/
`audit_log_repository` collaborators (all default None): the state
transition itself always happens regardless (repository writes are never
optional), but cache refresh and audit logging are best-effort additions
-- a use case constructed with none of them (as every test below still
can) behaves identically to before this file existed. This mirrors how
EvaluateIncidentUseCase already treats its own optional collaborators."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.domain.entities.rule import Rule
from app.domain.entities.rule_pack import RulePack, DRAFT, PUBLISHED, ACTIVE, ARCHIVED, can_transition
from app.domain.entities.audit_log_entry import AuditLogEntry
from app.domain.interfaces.rule_pack_repository import RulePackRepository
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.interfaces.cache_refresh_notifier import CacheRefreshNotifier, CacheRefreshEvent
from app.domain.value_objects.rule_condition import RuleCondition
from app.application.use_cases.validate_rule_pack import ValidateRulePackUseCase


def _write_audit(
    audit_log_repository: Optional[AuditLogRepository], *, entity_id: str, action: str,
    actor: str, before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]],
    reason: Optional[str] = None, correlation_id: Optional[str] = None,
) -> None:
    if audit_log_repository is None:
        return
    audit_log_repository.save(AuditLogEntry(
        id=str(uuid.uuid4()), entity_type="rule_pack", entity_id=entity_id, action=action,
        actor=actor, before=before, after=after, ip_address=None, request_id=None,
        correlation_id=correlation_id, created_at=datetime.now(timezone.utc), reason=reason,
    ))


def _notify(notifier: Optional[CacheRefreshNotifier], *, entity_id: str, action: str) -> None:
    if notifier is None:
        return
    notifier.publish(CacheRefreshEvent(entity_type="rule_pack", entity_id=entity_id, action=action))


def _pack_snapshot(pack: RulePack) -> Dict[str, Any]:
    return {"id": pack.id, "name": pack.name, "version": pack.version, "status": pack.status}


class CreateRulePackUseCase:
    """Creates a new Draft rule pack. If a version isn't given, the next
    integer after the highest existing version for that name is assigned
    (starting at 1 for a brand-new name) -- callers never have to guess or
    race on version numbers themselves."""

    def __init__(self, repository: RulePackRepository, audit_log_repository: Optional[AuditLogRepository] = None):
        self.repository = repository
        self.audit_log_repository = audit_log_repository

    def execute(
        self, name: str, region: Optional[str] = None, tenant_id: Optional[str] = None,
        rules: Optional[List[Rule]] = None, actor: str = "system", correlation_id: Optional[str] = None,
    ) -> RulePack:
        existing_versions = [p.version for p in self.repository.list_versions(name)]
        latest_version = max(existing_versions) if existing_versions else None
        next_version = (latest_version + 1) if latest_version is not None else 1
        pack = RulePack(
            name=name, version=next_version, status=DRAFT, region=region,
            rules=list(rules or []), tenant_id=tenant_id, created_by=actor,
            parent_version=latest_version,
        )
        saved = self.repository.save(pack)
        _write_audit(
            self.audit_log_repository, entity_id=saved.id, action="created", actor=actor,
            before=None, after=_pack_snapshot(saved), correlation_id=correlation_id,
        )
        return saved


class UpdateRulePackMetadataUseCase:
    """Editors may modify a Draft; publishing freezes metadata (Published/
    Active/Deprecated packs are immutable except for status transitions --
    change means a new version, per the spec's versioning model)."""

    def __init__(self, repository: RulePackRepository, audit_log_repository: Optional[AuditLogRepository] = None):
        self.repository = repository
        self.audit_log_repository = audit_log_repository

    def execute(
        self, pack_id: str, actor: str = "system", correlation_id: Optional[str] = None,
        expected_lock_version: Optional[int] = None, **fields,
    ) -> RulePack:
        pack = self.repository.get_by_id(pack_id)
        if pack is None:
            raise ValueError(f"No such rule pack: {pack_id}")
        if pack.status != DRAFT:
            raise ValueError(f"Cannot modify a {pack.status} rule pack -- only Draft packs are editable; create a new version instead")
        before = _pack_snapshot(pack)
        updated = self.repository.update_metadata(pack_id, expected_lock_version=expected_lock_version, **fields)
        _write_audit(
            self.audit_log_repository, entity_id=pack_id, action="updated", actor=actor,
            before=before, after=_pack_snapshot(updated), correlation_id=correlation_id,
        )
        return updated


class SoftDeleteRulePackUseCase:
    """Policy-Admin-only. Refuses to archive the currently active version
    directly -- activate a different version (or roll back) first, so
    there's never a moment where the hot path's get_active() comes up
    empty because the only active pack was just deleted out from under
    it."""

    def __init__(
        self, repository: RulePackRepository, cache=None,
        notifier: Optional[CacheRefreshNotifier] = None, audit_log_repository: Optional[AuditLogRepository] = None,
    ):
        self.repository = repository
        self.cache = cache
        self.notifier = notifier
        self.audit_log_repository = audit_log_repository

    def execute(
        self, pack_id: str, actor: str = "system", reason: Optional[str] = None,
        correlation_id: Optional[str] = None, expected_lock_version: Optional[int] = None,
    ) -> RulePack:
        pack = self.repository.get_by_id(pack_id)
        if pack is None:
            raise ValueError(f"No such rule pack: {pack_id}")
        if pack.status == ACTIVE:
            raise ValueError("Cannot delete the active rule pack -- activate a different version first")
        before = _pack_snapshot(pack)
        deleted = self.repository.soft_delete(pack_id, expected_lock_version=expected_lock_version)
        _notify(self.notifier, entity_id=pack_id, action="deleted")
        _write_audit(
            self.audit_log_repository, entity_id=pack_id, action="deleted", actor=actor,
            before=before, after=_pack_snapshot(deleted), reason=reason, correlation_id=correlation_id,
        )
        return deleted


class PublishRulePackUseCase:
    """Draft -> Published. Runs ValidateRulePackUseCase first -- an invalid
    pack can never be published, matching "No request should use Draft
    policies" by construction (Draft packs can't even reach Active without
    passing through this validated gate)."""

    def __init__(
        self, repository: RulePackRepository, validator: Optional[ValidateRulePackUseCase] = None,
        audit_log_repository: Optional[AuditLogRepository] = None,
    ):
        self.repository = repository
        self.validator = validator or ValidateRulePackUseCase()
        self.audit_log_repository = audit_log_repository

    def execute(self, pack_id: str, actor: str = "system", correlation_id: Optional[str] = None) -> RulePack:
        pack = self.repository.get_by_id(pack_id)
        if pack is None:
            raise ValueError(f"No such rule pack: {pack_id}")
        if not can_transition(pack.status, PUBLISHED):
            raise ValueError(f"Cannot publish a rule pack in status '{pack.status}'")
        result = self.validator.execute(pack)
        if not result.is_valid:
            raise ValueError(f"Cannot publish an invalid rule pack: {'; '.join(result.errors)}")
        before = _pack_snapshot(pack)
        updated = self.repository.update_status(pack_id, PUBLISHED)
        _write_audit(
            self.audit_log_repository, entity_id=pack_id, action="published", actor=actor,
            before=before, after=_pack_snapshot(updated), correlation_id=correlation_id,
        )
        return updated


class ActivateRulePackUseCase:
    """Published (or Deprecated, for rollback) -> Active. Deprecates
    whatever was previously active for the same name (repository.activate()
    already does this atomically), stamps activated_at, refreshes the
    cache, and writes an audit entry. This is the only path that makes a
    rule pack live -- Draft/Published packs are never read by
    get_active()."""

    def __init__(
        self, repository: RulePackRepository, cache=None,
        notifier: Optional[CacheRefreshNotifier] = None, audit_log_repository: Optional[AuditLogRepository] = None,
    ):
        self.repository = repository
        self.cache = cache
        self.notifier = notifier
        self.audit_log_repository = audit_log_repository

    def execute(
        self, pack_id: str, actor: str = "system", reason: Optional[str] = None,
        correlation_id: Optional[str] = None, expected_lock_version: Optional[int] = None,
    ) -> RulePack:
        pack = self.repository.get_by_id(pack_id)
        if pack is None:
            raise ValueError(f"No such rule pack: {pack_id}")
        if not can_transition(pack.status, ACTIVE):
            raise ValueError(
                f"Cannot activate a rule pack in status '{pack.status}' -- publish it first "
                f"(or it must be 'deprecated' for a rollback-style re-activation)"
            )
        before = _pack_snapshot(pack)
        activated = self.repository.activate(pack.name, pack.version, expected_lock_version=expected_lock_version)
        _notify(self.notifier, entity_id=pack_id, action="activated")
        _write_audit(
            self.audit_log_repository, entity_id=pack_id, action="activated", actor=actor,
            before=before, after=_pack_snapshot(activated), reason=reason, correlation_id=correlation_id,
        )
        return activated


class ExportRulePackUseCase:
    """Active rule pack -> plain JSON-serializable dict, for migration
    between environments (spec: "Export active rule pack as JSON")."""

    def __init__(self, repository: RulePackRepository):
        self.repository = repository

    def execute(self, name: str, region: Optional[str] = None) -> Dict[str, Any]:
        pack = self.repository.get_active(name, region=region)
        if pack is None:
            raise ValueError(f"No active rule pack named '{name}' for region={region!r}")
        return {
            "name": pack.name,
            "version": pack.version,
            "region": pack.region,
            "rules": [_rule_to_json(r) for r in pack.rules],
        }


class ImportRulePackUseCase:
    """JSON -> a new Draft rule pack version. Per spec: reject outright if
    an identical version (same name+version) already exists; if the rule
    content differs from the latest existing version of that name, create
    the next version rather than overwriting anything published/active
    ("JSON should NEVER overwrite an existing published rule pack unless
    explicitly imported" -- importing IS the explicit action; it still
    never overwrites, it only ever adds a new Draft)."""

    def __init__(self, repository: RulePackRepository, audit_log_repository: Optional[AuditLogRepository] = None):
        self.repository = repository
        self.audit_log_repository = audit_log_repository

    def execute(self, document: Dict[str, Any], actor: str = "system", correlation_id: Optional[str] = None) -> RulePack:
        name = document["name"]
        requested_version = document.get("version")
        rules = [_rule_from_json(r) for r in document.get("rules", [])]

        if requested_version is not None and self.repository.get(name, requested_version) is not None:
            raise ValueError(f"Rule pack '{name}' version {requested_version} already exists -- import rejected")

        existing_versions = self.repository.list_versions(name)
        latest_version = max((p.version for p in existing_versions), default=None)
        next_version = requested_version or ((latest_version or 0) + 1)

        pack = RulePack(
            name=name, version=next_version, status=DRAFT, region=document.get("region"),
            rules=rules, tenant_id=document.get("tenantId"), created_by=actor,
            parent_version=latest_version,
        )
        saved = self.repository.save(pack)
        _write_audit(
            self.audit_log_repository, entity_id=saved.id, action="imported", actor=actor,
            before=None, after=_pack_snapshot(saved), correlation_id=correlation_id,
        )
        return saved


def _rule_to_json(rule: Rule) -> Dict[str, Any]:
    return {
        "id": rule.id, "ruleCode": rule.rule_code, "name": rule.name, "description": rule.description,
        "family": rule.family, "familyOrder": rule.family_order, "priorityWeight": rule.priority_weight,
        "severityBand": rule.severity_band, "contributionScore": rule.contribution_score,
        "conditions": rule.conditions.tree, "exceptions": rule.exceptions.tree if rule.exceptions else None,
        "conflictGroup": rule.conflict_group, "conflictsWith": rule.conflicts_with,
        "isSuppressor": rule.is_suppressor, "nonSuppressible": rule.non_suppressible,
        "cooldownMinutes": rule.cooldown_minutes, "actions": rule.actions, "mitigations": rule.mitigations,
        "sequencing": rule.sequencing, "slaTarget": rule.sla_target,
        "ruleStatus": rule.rule_status, "enabled": rule.enabled,
    }


def _rule_from_json(data: Dict[str, Any]) -> Rule:
    return Rule(
        rule_code=data["ruleCode"], name=data["name"], description=data.get("description", ""),
        family=data.get("family", "OPERATIONAL_FEASIBILITY"), family_order=data.get("familyOrder", 99),
        priority_weight=data.get("priorityWeight", 50), severity_band=data.get("severityBand"),
        contribution_score=data.get("contributionScore"),
        conditions=RuleCondition(data["conditions"]),
        exceptions=RuleCondition(data["exceptions"]) if data.get("exceptions") else None,
        conflict_group=data.get("conflictGroup"), conflicts_with=list(data.get("conflictsWith", [])),
        is_suppressor=data.get("isSuppressor", False), non_suppressible=data.get("nonSuppressible", False),
        cooldown_minutes=data.get("cooldownMinutes", 0), actions=data.get("actions", {}),
        mitigations=data.get("mitigations", {}), sequencing=data.get("sequencing"),
        sla_target=data.get("slaTarget"), rule_status=data.get("ruleStatus", "ACTIVE"),
        enabled=data.get("enabled", True),
    )
