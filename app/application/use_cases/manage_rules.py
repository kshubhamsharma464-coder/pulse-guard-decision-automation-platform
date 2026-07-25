"""Individual-rule CRUD for the dynamic Rule Management platform
(docs/rule-management.md). A Rule is always a child of a RulePack
aggregate (the same modeling this codebase has used from the start --
RulePack owns rules, there's no independent "rules" table row without a
rule_set_id) -- these use cases operate on a rule inside its parent pack,
which must be in Draft status (editors may create/modify drafts; a
Published/Active/Deprecated pack's rules are frozen, per the spec's
versioning model -- change means a new version).

Known limitation, documented rather than hidden: get/update/delete-by-id
and list-across-packs do a linear scan over RulePackRepository.list_all()
rather than an independent indexed rules table, since rules aren't queried
independently of their pack anywhere else in this codebase. Fine at this
project's scale (hundreds of rules across a handful of packs); a real
high-volume deployment would add a dedicated rule-lookup index or table.
See docs/rule-management.md."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.domain.entities.rule import Rule
from app.domain.entities.rule_pack import RulePack, DRAFT
from app.domain.entities.audit_log_entry import AuditLogEntry
from app.domain.interfaces.rule_pack_repository import RulePackRepository
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.application.use_cases.rule_pack_lifecycle import _rule_to_json, _rule_from_json
from app.application.use_cases.validate_rule_pack import ValidateRulePackUseCase, ValidationResult


def _write_audit(
    audit_log_repository: Optional[AuditLogRepository], *, entity_id: str, action: str,
    actor: str, before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]],
    reason: Optional[str] = None, correlation_id: Optional[str] = None,
) -> None:
    if audit_log_repository is None:
        return
    audit_log_repository.save(AuditLogEntry(
        id=str(uuid.uuid4()), entity_type="rule", entity_id=entity_id, action=action,
        actor=actor, before=before, after=after, ip_address=None, request_id=None,
        correlation_id=correlation_id, created_at=datetime.now(timezone.utc), reason=reason,
    ))


def _find_rule(repository: RulePackRepository, rule_id: str) -> Tuple[Optional[RulePack], Optional[Rule]]:
    for pack in repository.list_all(include_archived=True, limit=10_000):
        for rule in pack.rules:
            if rule.id == rule_id:
                return pack, rule
    return None, None


class CreateRuleUseCase:
    def __init__(self, repository: RulePackRepository, audit_log_repository: Optional[AuditLogRepository] = None):
        self.repository = repository
        self.audit_log_repository = audit_log_repository

    def execute(self, pack_id: str, rule_data: Dict[str, Any], actor: str = "system", correlation_id: Optional[str] = None) -> Rule:
        pack = self.repository.get_by_id(pack_id)
        if pack is None:
            raise ValueError(f"No such rule pack: {pack_id}")
        if pack.status != DRAFT:
            raise ValueError(f"Cannot add rules to a {pack.status} rule pack -- only Draft packs are editable")
        rule = _rule_from_json(rule_data)
        if any(r.rule_code == rule.rule_code for r in pack.rules):
            raise ValueError(f"Rule code '{rule.rule_code}' already exists in rule pack {pack_id}")
        # App-generated id, threaded through to the ORM row on save (see
        # rule_to_orm's docstring) -- both backends end up with the same id
        # the caller gets back, no post-save lookup needed.
        rule.id = rule.id or str(uuid.uuid4())
        pack.rules.append(rule)
        self.repository.save(pack)
        _write_audit(
            self.audit_log_repository, entity_id=rule.id, action="created", actor=actor,
            before=None, after=_rule_to_json(rule), correlation_id=correlation_id,
        )
        return rule


class GetRuleUseCase:
    def __init__(self, repository: RulePackRepository):
        self.repository = repository

    def execute(self, rule_id: str) -> Rule:
        _, rule = _find_rule(self.repository, rule_id)
        if rule is None:
            raise ValueError(f"No such rule: {rule_id}")
        return rule


class ListRulesUseCase:
    def __init__(self, repository: RulePackRepository):
        self.repository = repository

    def execute(self, pack_id: Optional[str] = None, family: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Rule]:
        if pack_id is not None:
            pack = self.repository.get_by_id(pack_id)
            rules = list(pack.rules) if pack else []
        else:
            rules = [r for pack in self.repository.list_all(limit=10_000) for r in pack.rules]
        if family is not None:
            rules = [r for r in rules if r.family == family]
        return rules[offset: offset + limit]


class UpdateRuleUseCase:
    def __init__(self, repository: RulePackRepository, audit_log_repository: Optional[AuditLogRepository] = None):
        self.repository = repository
        self.audit_log_repository = audit_log_repository

    def execute(self, rule_id: str, rule_data: Dict[str, Any], actor: str = "system", correlation_id: Optional[str] = None) -> Rule:
        pack, rule = _find_rule(self.repository, rule_id)
        if rule is None:
            raise ValueError(f"No such rule: {rule_id}")
        if pack.status != DRAFT:
            raise ValueError(f"Cannot modify a rule in a {pack.status} rule pack -- only Draft packs are editable")
        before = _rule_to_json(rule)

        merged = {**before, **rule_data}
        merged["id"] = rule.id
        updated_rule = _rule_from_json(merged)
        updated_rule.id = rule.id

        pack.rules = [updated_rule if r.id == rule_id else r for r in pack.rules]
        self.repository.save(pack)
        _write_audit(
            self.audit_log_repository, entity_id=rule_id, action="updated", actor=actor,
            before=before, after=_rule_to_json(updated_rule), correlation_id=correlation_id,
        )
        return updated_rule


class DeleteRuleUseCase:
    """Soft delete -- sets enabled=False (the same flag Rule.is_active()
    already checks, per is_active()'s existing `enabled and rule_status ==
    'ACTIVE'` contract) rather than removing the row, so the rule stays
    visible/auditable but never matches during evaluation."""

    def __init__(self, repository: RulePackRepository, audit_log_repository: Optional[AuditLogRepository] = None):
        self.repository = repository
        self.audit_log_repository = audit_log_repository

    def execute(self, rule_id: str, actor: str = "system", reason: Optional[str] = None, correlation_id: Optional[str] = None) -> Rule:
        pack, rule = _find_rule(self.repository, rule_id)
        if rule is None:
            raise ValueError(f"No such rule: {rule_id}")
        if pack.status != DRAFT:
            raise ValueError(f"Cannot delete a rule in a {pack.status} rule pack -- only Draft packs are editable")
        before = _rule_to_json(rule)
        rule.enabled = False
        self.repository.save(pack)
        _write_audit(
            self.audit_log_repository, entity_id=rule_id, action="deleted", actor=actor,
            before=before, after=_rule_to_json(rule), reason=reason, correlation_id=correlation_id,
        )
        return rule


class BulkCreateRulesUseCase:
    def __init__(self, create_rule_use_case: CreateRuleUseCase):
        self.create_rule_use_case = create_rule_use_case

    def execute(self, pack_id: str, rules_data: List[Dict[str, Any]], actor: str = "system") -> List[Rule]:
        return [self.create_rule_use_case.execute(pack_id, data, actor=actor) for data in rules_data]


class ValidateRuleUseCase:
    """Structural validation of a single rule payload (conditions tree
    well-formed, conflictsWith targets exist within its own siblings, if
    supplied) -- wraps ValidateRulePackUseCase against a throwaway
    single-rule pack rather than duplicating its checks."""

    def __init__(self, sibling_rules: Optional[List[Rule]] = None):
        self._pack_validator = ValidateRulePackUseCase()
        self.sibling_rules = sibling_rules or []

    def execute(self, rule_data: Dict[str, Any]) -> ValidationResult:
        try:
            rule = _rule_from_json(rule_data)
        except (KeyError, TypeError, ValueError) as exc:
            return ValidationResult(is_valid=False, errors=[f"Malformed rule payload: {exc}"])
        throwaway = RulePack(name="__validate__", version=0, status=DRAFT, region=None, rules=[rule, *self.sibling_rules])
        return self._pack_validator.execute(throwaway)


class RuleHistoryUseCase:
    def __init__(self, audit_log_repository: AuditLogRepository):
        self.audit_log_repository = audit_log_repository

    def execute(self, rule_id: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[AuditLogEntry]:
        if rule_id is not None:
            return self.audit_log_repository.list_by_entity("rule", rule_id)
        return self.audit_log_repository.list_by_entity_type("rule", limit=limit, offset=offset)
