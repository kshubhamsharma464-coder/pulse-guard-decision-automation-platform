"""SQLAlchemy ORM models -- a 1:1 mapping onto app/infrastructure/database/schema.sql,
which was designed at the very start of this project and already covers
nearly everything the DecisioX spec's entity list asks for. Rather than
inventing a parallel/competing shape, this file makes that existing,
carefully-considered schema real.

Mapping from the DecisioX spec's requested entities to what's here:
  Rule            -> RuleORM
  RuleVersion     -> RuleSetORM (a "rule set" IS a version -- draft/
                     validated/shadow/active/deprecated/rolled_back,
                     with parent_version_id for rollback lineage; this is
                     exactly what "RuleVersion" describes, just named for
                     what it already was in this project's design doc)
  Decision        -> DecisionORM
  DecisionAudit   -> AuditLogORM, filtered to entity_type='decision'
                     (a general-purpose audit_log table, per schema.sql,
                     rather than a second table duplicating its shape)
  EvaluationHistory -> DecisionORM rows are append-only per incident_id
                     (see InMemoryDecisionRepository's own docstring) --
                     the full history already exists, it doesn't need a
                     separate table
  AuditLog        -> AuditLogORM
  RequestLog      -> RequestLogORM (genuinely new -- schema.sql had no
                     HTTP-request-level logging table)
  User/Role/Permission/APIKey -> UserORM/RoleORM/PermissionORM/APIKeyORM,
                     added in Phase 2 alongside the auth feature work that
                     actually reads/writes them (see docs/auth.md).
  Simulation      -> deliberately NOT added yet; belongs with the
                     simulation (Phase 4) feature work.

Soft-delete (`deleted_at`) and optimistic locking (`lock_version`) are
applied only to RuleSetORM and RuleORM -- see base.py's docstring for why
the append-only tables deliberately don't get them."""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Integer, Boolean, Text, ForeignKey, UniqueConstraint, Index,
    Numeric, ARRAY, DateTime,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship, declared_attr

from app.infrastructure.db.base import (
    Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, OptimisticLockMixin, SqliteUUID,
)

# JSONB on Postgres (native, GIN-indexable, matches schema.sql exactly);
# plain JSON on SQLite (test-only fallback -- see infrastructure/db/session.py).
_JSONB = JSONB().with_variant(JSON(), "sqlite")
_UUID_FK = PG_UUID(as_uuid=True).with_variant(SqliteUUID(), "sqlite")


class RuleSetORM(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, OptimisticLockMixin):
    """== rule_sets in schema.sql == the "RuleVersion" entity.

    Phase 5 (docs/policy-platform.md, "Concurrency"): version_id_col is
    now wired for real, not advisory -- lock_version (from
    OptimisticLockMixin) is a genuine SQLAlchemy version counter.
    SQLAlchemy appends `WHERE lock_version = <the value that was loaded>`
    to every UPDATE against this table and auto-increments it on success;
    if a concurrent writer already changed the row (and therefore its
    lock_version) since this session loaded it, zero rows match the WHERE
    clause and SQLAlchemy raises StaleDataError on commit/flush --
    PostgresRulePackRepository catches that and re-raises
    ConcurrentModificationError (app/domain/exceptions.py), which a
    global FastAPI exception handler (main.py) turns into 409 Conflict.
    This is what makes "100+ business users editing rules... no dirty
    reads... no inconsistent policy state" a real, enforced guarantee
    rather than a design intention -- deliberately scoped to RuleSetORM
    only (the "policy version" entity this requirement is actually
    about), not RuleORM, whose rows are always rewritten wholesale as
    part of their parent rule pack's save() rather than updated
    individually."""

    __tablename__ = "rule_sets"
    __table_args__ = (
        UniqueConstraint("name", "version", "region", "tenant_id", name="ux_rule_set_version"),
        Index("idx_rule_sets_active_lookup", "name", "region", "tenant_id", "status"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    region: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(_UUID_FK, nullable=True)
    parent_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        _UUID_FK, ForeignKey("rule_sets.id"), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, default="system")
    # Was originally typed as a bare Optional[str] (an oversight -- same
    # class of bug as the Phase-1 timestamp-as-string issue documented in
    # docs/persistence.md, missed here at the time). Fixed to a real
    # DateTime column in migration 0003 -- see that migration's docstring.
    activated_at: Mapped[Optional["datetime"]] = mapped_column(DateTime(timezone=True), nullable=True)

    rules: Mapped[list["RuleORM"]] = relationship(back_populates="rule_set", cascade="all, delete-orphan")

    # declared_attr, not a plain dict: `lock_version` is defined on the
    # OptimisticLockMixin, not directly on this class body, so it isn't a
    # resolvable name yet while this class's body is executing -- SQLAlchemy
    # defers evaluation of a declared_attr until the class is fully built
    # (mapper-configuration time), at which point `cls.lock_version`
    # correctly resolves to the mixin's mapped column.
    @declared_attr
    def __mapper_args__(cls):
        return {"version_id_col": cls.lock_version}


class RuleORM(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, OptimisticLockMixin):
    """== rules in schema.sql."""

    __tablename__ = "rules"
    __mapper_args__ = {"version_id_col": None}
    __table_args__ = (
        UniqueConstraint("rule_set_id", "rule_code", name="ux_rule_code_per_set"),
        Index("idx_rules_active", "rule_set_id", "enabled", "rule_status"),
        Index("idx_rules_family_order", "rule_set_id", "family_order", "priority_weight"),
    )

    rule_set_id: Mapped[uuid.UUID] = mapped_column(_UUID_FK, ForeignKey("rule_sets.id", ondelete="CASCADE"), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    priority_weight: Mapped[int] = mapped_column(Integer, nullable=False)
    severity_band: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    contribution_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    family: Mapped[str] = mapped_column(String(40), nullable=False)
    family_order: Mapped[int] = mapped_column(Integer, nullable=False)

    conditions: Mapped[dict] = mapped_column(_JSONB, nullable=False)
    exceptions: Mapped[Optional[dict]] = mapped_column(_JSONB, nullable=True)
    conflict_group: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    conflicts_with: Mapped[list] = mapped_column(
        ARRAY(String).with_variant(JSON(), "sqlite"), nullable=False, default=list
    )
    is_suppressor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    non_suppressible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    actions: Mapped[dict] = mapped_column(_JSONB, nullable=False)
    mitigations: Mapped[dict] = mapped_column(_JSONB, nullable=False, default=dict)
    sequencing: Mapped[Optional[dict]] = mapped_column(_JSONB, nullable=True)
    sla_target: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    region: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(_UUID_FK, nullable=True)

    rule_status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_by: Mapped[str] = mapped_column(String(100), nullable=False, default="system")
    approved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    rule_set: Mapped["RuleSetORM"] = relationship(back_populates="rules")


class DecisionORM(Base, UUIDPrimaryKeyMixin):
    """== decisions in schema.sql. Append-only: no soft-delete/optimistic-
    locking mixins -- a Decision is never edited, only ever appended
    alongside prior decisions for the same incident (matches
    InMemoryDecisionRepository's exact semantics)."""

    __tablename__ = "decisions"
    __table_args__ = (Index("idx_decisions_incident", "incident_id"),)

    incident_id: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_set_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    rule_set_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    priority: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    risk_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    risk_band: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    decision: Mapped[dict] = mapped_column(_JSONB, nullable=False)          # actions
    mitigations: Mapped[dict] = mapped_column(_JSONB, nullable=False, default=dict)
    execution_plan: Mapped[list] = mapped_column(_JSONB, nullable=False, default=list)
    matched_rules: Mapped[list] = mapped_column(_JSONB, nullable=False, default=list)
    rejected_rules: Mapped[list] = mapped_column(_JSONB, nullable=False, default=list)
    suppressed_rules: Mapped[list] = mapped_column(_JSONB, nullable=False, default=list)
    compliance_constraints: Mapped[list] = mapped_column(_JSONB, nullable=False, default=list)

    confidence_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    degraded_context: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False, default="0.1.0")
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), nullable=False)


class ManualOverrideORM(Base, UUIDPrimaryKeyMixin):
    """== manual_overrides. Append-only, per design doc §6.6.

    decision_id is a plain string, not a UUID foreign key to decisions.id
    -- deliberately, matching EscalationEventORM below and the domain
    reality: the Decision dataclass (app/domain/entities/decision.py) has
    no `id` field, only incident_id; every existing call site treats
    "decision_id" as an opaque business-level string. schema.sql's
    original design modeled a real FK here, which would require adding an
    id field to Decision and threading it through every use case that
    creates one -- a real improvement, but out of scope for this
    persistence-only phase; flagged rather than silently forced."""

    __tablename__ = "manual_overrides"

    decision_id: Mapped[str] = mapped_column(String(50), nullable=False)
    operator: Mapped[str] = mapped_column(String(100), nullable=False)
    original_decision: Mapped[dict] = mapped_column(_JSONB, nullable=False)
    override_decision: Mapped[dict] = mapped_column(_JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), nullable=False)


class EscalationPolicyORM(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "escalation_policies"

    severity_band: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    levels: Mapped[list] = mapped_column(_JSONB, nullable=False)  # [{"level": "...", "timeoutMinutes": N}, ...]


class EscalationEventORM(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "escalation_events"
    __table_args__ = (Index("idx_escalation_events_decision", "decision_id", "triggered_at"),)

    decision_id: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[str] = mapped_column(String(30), nullable=False)
    triggered_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[Optional["datetime"]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class AuditLogORM(Base, UUIDPrimaryKeyMixin):
    """== audit_log. Immutable by construction: no update/delete method is
    ever exposed on its repository -- see postgres_audit_log_repository.py."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("idx_audit_entity", "entity_type", "entity_id", "created_at"),)

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    before: Mapped[Optional[dict]] = mapped_column(_JSONB, nullable=True)
    after: Mapped[Optional[dict]] = mapped_column(_JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # added in migration 0003


class RequestLogORM(Base, UUIDPrimaryKeyMixin):
    """New table -- not in the original schema.sql. HTTP-request-level
    logging (method/path/status/duration), distinct from AuditLogORM
    (business-entity mutations) and from structured application logs
    (which stay in stdout/log aggregation, not the database)."""

    __tablename__ = "request_log"
    __table_args__ = (Index("idx_request_log_request_id", "request_id"),)

    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), nullable=False)


# -- Phase 2: Auth -----------------------------------------------------

class UserORM(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, OptimisticLockMixin):
    """A genuinely mutable entity (profile fields, role assignment change
    over a user's lifetime) -- gets the full mixin set, like RuleSetORM/
    RuleORM in Phase 1."""

    __tablename__ = "users"
    __mapper_args__ = {"version_id_col": None}

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    roles: Mapped[list] = mapped_column(_JSONB, nullable=False, default=list)  # list[str] role codes
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[Optional["datetime"]] = mapped_column(DateTime(timezone=True), nullable=True)


class RoleORM(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Catalog-like -- small, admin-managed, rarely concurrently edited.
    No soft-delete/optimistic-lock mixins, same reasoning as PermissionORM
    below (see base.py's docstring for the general rule)."""

    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    permissions: Mapped[list] = mapped_column(_JSONB, nullable=False, default=list)  # list[str] permission codes
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")


class PermissionORM(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Reference catalog of grantable permission codes. Almost never
    written after initial seeding, so no soft-delete/optimistic-lock."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")


class APIKeyORM(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Revocation is modeled as `is_active=False`, not soft-delete (a
    revoked key still needs to be queryable/listable in the admin UI --
    `deleted_at` would conflate "revoked" with "hidden from lookups", which
    every other soft-deleted entity in this codebase implies)."""

    __tablename__ = "api_keys"
    __table_args__ = (Index("idx_api_keys_prefix", "key_prefix"),)

    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    hashed_key: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(_UUID_FK, nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    roles: Mapped[list] = mapped_column(_JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_used_at: Mapped[Optional["datetime"]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional["datetime"]] = mapped_column(DateTime(timezone=True), nullable=True)


class IncidentORM(Base):
    """Persisted Incident resource (added in migration 0003, alongside the
    /api/v1/incidents CRUD surface -- docs/rule-management.md). Keyed by
    incident_id directly (the caller-supplied business identifier), not a
    generated UUID -- same natural-key convention this codebase already
    uses for decision_id on ManualOverrideORM/EscalationEventORM."""

    __tablename__ = "incidents"

    incident_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    payload: Mapped[dict] = mapped_column(_JSONB, nullable=False, default=dict)
    enriched_context: Mapped[dict] = mapped_column(_JSONB, nullable=False, default=dict)
    degraded_context: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    context_sources_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    context_sources_degraded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="received")
    region: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(_UUID_FK, nullable=True)
    created_at: Mapped["datetime"] = mapped_column(DateTime(timezone=True), nullable=False)
