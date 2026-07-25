"""Bidirectional conversion between domain entities (app/domain/entities/,
what PolicyEngine/ConflictResolver/etc. actually operate on) and ORM rows
(app/infrastructure/db/models.py, what gets persisted). Kept in one place
so every Postgres-backed repository uses the identical mapping -- domain
code never imports SQLAlchemy, and these functions are the only place that
knows both shapes."""

import uuid
from datetime import datetime, timezone
from typing import Optional
from app.domain.entities.rule import Rule
from app.domain.entities.rule_pack import RulePack
from app.domain.entities.decision import Decision, MatchedRuleTrace, RejectedRuleTrace
from app.domain.entities.manual_override import ManualOverride
from app.domain.entities.escalation import EscalationPolicy, EscalationLevel, EscalationEvent
from app.domain.entities.user import User
from app.domain.entities.role import Role
from app.domain.entities.permission import Permission
from app.domain.entities.api_key import APIKey
from app.domain.entities.incident import Incident
from app.domain.value_objects.rule_condition import RuleCondition
from app.infrastructure.db.models import (
    RuleSetORM, RuleORM, DecisionORM, ManualOverrideORM,
    EscalationPolicyORM, EscalationEventORM, UserORM, RoleORM, PermissionORM, APIKeyORM, IncidentORM,
)


def rule_to_domain(row: RuleORM) -> Rule:
    return Rule(
        id=str(row.id),
        rule_code=row.rule_code,
        name=row.name,
        description=row.description or "",
        family=row.family,
        family_order=row.family_order,
        priority_weight=row.priority_weight,
        severity_band=row.severity_band,
        contribution_score=row.contribution_score,
        conditions=RuleCondition(row.conditions),
        exceptions=RuleCondition(row.exceptions) if row.exceptions else None,
        conflict_group=row.conflict_group,
        conflicts_with=list(row.conflicts_with or []),
        is_suppressor=row.is_suppressor,
        non_suppressible=row.non_suppressible,
        cooldown_minutes=row.cooldown_minutes,
        actions=row.actions or {},
        mitigations=row.mitigations or {},
        sequencing=row.sequencing,
        sla_target=row.sla_target,
        rule_status=row.rule_status,
        enabled=row.enabled,
    )


def rule_to_orm(rule: Rule, rule_set_id) -> RuleORM:
    # id is only passed through if the domain Rule already has one (set by
    # CreateRuleUseCase for app-generated rules) -- explicitly passing
    # id=None would suppress the column's default=uuid.uuid4 (SQLAlchemy
    # only applies a mapped_column default when the attribute is never
    # set at all), so fixture-loaded rules (rule.id is always None) still
    # get a fresh server-side-equivalent UUID exactly as before.
    extra = {"id": _to_uuid(rule.id)} if rule.id else {}
    return RuleORM(
        **extra,
        rule_set_id=rule_set_id,
        rule_code=rule.rule_code,
        name=rule.name,
        description=rule.description,
        family=rule.family,
        family_order=rule.family_order,
        priority_weight=rule.priority_weight,
        severity_band=rule.severity_band,
        contribution_score=rule.contribution_score,
        conditions=rule.conditions.tree,
        exceptions=rule.exceptions.tree if rule.exceptions else None,
        conflict_group=rule.conflict_group,
        conflicts_with=list(rule.conflicts_with or []),
        is_suppressor=rule.is_suppressor,
        non_suppressible=rule.non_suppressible,
        cooldown_minutes=rule.cooldown_minutes,
        actions=rule.actions,
        mitigations=rule.mitigations,
        sequencing=rule.sequencing,
        sla_target=rule.sla_target,
        rule_status=rule.rule_status,
        enabled=rule.enabled,
    )


def rule_pack_to_domain(row: RuleSetORM) -> RulePack:
    parent_version = None
    # parent_version_id references another rule_sets row; RulePack only
    # stores the parent's integer version, not its UUID, so this is
    # resolved by the repository (which has the session) before calling
    # this mapper -- see PostgresRulePackRepository._resolve_parent_version.
    return RulePack(
        name=row.name,
        version=row.version,
        status=row.status,
        region=row.region,
        rules=[rule_to_domain(r) for r in row.rules if r.enabled or True],
        parent_version=parent_version,
    )


def decision_to_domain(row: DecisionORM) -> Decision:
    return Decision(
        incident_id=row.incident_id,
        priority=row.priority,
        risk_score=row.risk_score or 0,
        risk_band=row.risk_band or "LOW",
        actions=row.decision or {},
        mitigations=row.mitigations or {},
        execution_plan=row.execution_plan or [],
        matched_rules=[MatchedRuleTrace(**m) for m in (row.matched_rules or [])],
        rejected_rules=[RejectedRuleTrace(**r) for r in (row.rejected_rules or [])],
        suppressed_rules=row.suppressed_rules or [],
        compliance_constraints=row.compliance_constraints or [],
        confidence_score=float(row.confidence_score) if row.confidence_score is not None else 0.0,
        degraded_context=row.degraded_context,
        explanation=row.explanation,
        engine_version=row.engine_version,
        created_at=_parse_dt(row.created_at),
        resolved=row.resolved,
    )


def decision_to_orm(decision: Decision) -> DecisionORM:
    return DecisionORM(
        incident_id=decision.incident_id,
        priority=decision.priority,
        risk_score=decision.risk_score,
        risk_band=decision.risk_band,
        decision=decision.actions,
        mitigations=decision.mitigations,
        execution_plan=decision.execution_plan,
        matched_rules=[m.__dict__ for m in decision.matched_rules],
        rejected_rules=[r.__dict__ for r in decision.rejected_rules],
        suppressed_rules=decision.suppressed_rules,
        compliance_constraints=decision.compliance_constraints,
        confidence_score=decision.confidence_score,
        degraded_context=decision.degraded_context,
        explanation=decision.explanation,
        engine_version=decision.engine_version,
        resolved=decision.resolved,
        created_at=decision.created_at,
    )


def manual_override_to_domain(row: ManualOverrideORM) -> ManualOverride:
    return ManualOverride(
        id=str(row.id),
        decision_id=row.decision_id,
        operator=row.operator,
        original_decision=row.original_decision,
        override_decision=row.override_decision,
        reason=row.reason,
        created_at=_parse_dt(row.created_at),
    )


def manual_override_to_orm(override: ManualOverride) -> ManualOverrideORM:
    return ManualOverrideORM(
        decision_id=override.decision_id,
        operator=override.operator,
        original_decision=override.original_decision,
        override_decision=override.override_decision,
        reason=override.reason,
        created_at=override.created_at,
    )


def escalation_policy_to_domain(row: EscalationPolicyORM) -> EscalationPolicy:
    return EscalationPolicy(
        severity_band=row.severity_band,
        levels=[EscalationLevel(level=lvl["level"], timeout_minutes=lvl["timeoutMinutes"]) for lvl in row.levels],
    )


def escalation_policy_to_orm(policy: EscalationPolicy) -> EscalationPolicyORM:
    return EscalationPolicyORM(
        severity_band=policy.severity_band,
        levels=[{"level": lvl.level, "timeoutMinutes": lvl.timeout_minutes} for lvl in policy.levels],
    )


def escalation_event_to_domain(row: EscalationEventORM) -> EscalationEvent:
    return EscalationEvent(
        id=str(row.id),
        decision_id=row.decision_id,
        level=row.level,
        triggered_at=_parse_dt(row.triggered_at),
        acknowledged_at=_parse_dt(row.acknowledged_at) if row.acknowledged_at else None,
        acknowledged_by=row.acknowledged_by,
    )


def escalation_event_to_orm(event: EscalationEvent) -> EscalationEventORM:
    return EscalationEventORM(
        decision_id=event.decision_id,
        level=event.level,
        triggered_at=event.triggered_at,
        acknowledged_at=event.acknowledged_at,
        acknowledged_by=event.acknowledged_by,
    )


def _to_uuid(value) -> Optional[uuid.UUID]:
    """User/APIKey ids are generated app-side (see RegisterUserUseCase/
    CreateApiKeyUseCase) as plain strings, but UUID columns declared with
    as_uuid=True expect real uuid.UUID python objects on Postgres (the
    SQLite test substitute's TypeDecorator is lenient either way -- this
    matters for the real target dialect)."""
    if value is None:
        return None
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def user_to_domain(row: UserORM) -> User:
    return User(
        id=str(row.id),
        email=row.email,
        hashed_password=row.hashed_password,
        full_name=row.full_name,
        roles=list(row.roles or []),
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_login_at=row.last_login_at,
    )


def user_to_orm(user: User) -> UserORM:
    return UserORM(
        id=_to_uuid(user.id),
        email=user.email,
        hashed_password=user.hashed_password,
        full_name=user.full_name,
        roles=list(user.roles or []),
        is_active=user.is_active,
        last_login_at=user.last_login_at,
    )


def role_to_domain(row: RoleORM) -> Role:
    return Role(
        code=row.code, name=row.name, permissions=list(row.permissions or []),
        description=row.description, created_at=row.created_at, updated_at=row.updated_at,
    )


def role_to_orm(role: Role) -> RoleORM:
    return RoleORM(code=role.code, name=role.name, permissions=list(role.permissions or []), description=role.description)


def permission_to_domain(row: PermissionORM) -> Permission:
    return Permission(code=row.code, description=row.description, created_at=row.created_at)


def permission_to_orm(permission: Permission) -> PermissionORM:
    return PermissionORM(code=permission.code, description=permission.description)


def api_key_to_domain(row: APIKeyORM) -> APIKey:
    return APIKey(
        id=str(row.id),
        key_prefix=row.key_prefix,
        hashed_key=row.hashed_key,
        owner_user_id=str(row.owner_user_id) if row.owner_user_id else None,
        name=row.name,
        roles=list(row.roles or []),
        is_active=row.is_active,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        expires_at=row.expires_at,
    )


def api_key_to_orm(api_key: APIKey) -> APIKeyORM:
    return APIKeyORM(
        id=_to_uuid(api_key.id),
        key_prefix=api_key.key_prefix,
        hashed_key=api_key.hashed_key,
        owner_user_id=_to_uuid(api_key.owner_user_id),
        name=api_key.name,
        roles=list(api_key.roles or []),
        is_active=api_key.is_active,
        last_used_at=api_key.last_used_at,
        expires_at=api_key.expires_at,
    )


def incident_to_domain(row: IncidentORM) -> Incident:
    return Incident(
        incident_id=row.incident_id,
        payload=row.payload or {},
        enriched_context=row.enriched_context or {},
        degraded_context=row.degraded_context,
        context_sources_total=row.context_sources_total,
        context_sources_degraded=row.context_sources_degraded,
        status=row.status,
        region=row.region,
        tenant_id=str(row.tenant_id) if row.tenant_id else None,
        created_at=row.created_at,
    )


def incident_to_orm(incident: Incident) -> IncidentORM:
    return IncidentORM(
        incident_id=incident.incident_id,
        payload=incident.payload,
        enriched_context=incident.enriched_context,
        degraded_context=incident.degraded_context,
        context_sources_total=incident.context_sources_total,
        context_sources_degraded=incident.context_sources_degraded,
        status=incident.status,
        region=incident.region,
        tenant_id=_to_uuid(incident.tenant_id),
        created_at=incident.created_at,
    )


def _parse_dt(value) -> Optional[datetime]:
    """Defensive only -- columns are proper DateTime now, so `value` is
    already a datetime in normal operation. Handles the case where a
    string sneaks in (e.g. hand-inserted test fixtures)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
