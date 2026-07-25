"""Round-trip tests for every Postgres-backed repository, run against an
in-memory SQLite database via the exact same SQLAlchemy models
(app/infrastructure/db/models.py) that production points at real Postgres.
No live Postgres is available in CI/this sandbox; the JSONB/UUID columns
use .with_variant() specifically so this substitution is legitimate rather
than a mock -- same ORM mapping, same queries, only the dialect differs.

These are new tests, additive -- they don't touch or replace any existing
in-memory-repository test."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401 -- registers tables on Base.metadata

from app.infrastructure.repositories.postgres_rule_pack_repository import PostgresRulePackRepository
from app.infrastructure.repositories.postgres_rule_repository import PostgresRuleRepository
from app.infrastructure.repositories.postgres_decision_repository import PostgresDecisionRepository
from app.infrastructure.repositories.postgres_manual_override_repository import PostgresManualOverrideRepository
from app.infrastructure.repositories.postgres_escalation_repository import PostgresEscalationRepository
from app.infrastructure.repositories.postgres_escalation_policy_repository import PostgresEscalationPolicyRepository
from app.infrastructure.repositories.postgres_audit_log_repository import PostgresAuditLogRepository
from app.infrastructure.repositories.postgres_request_log_repository import PostgresRequestLogRepository

from app.domain.entities.rule import Rule
from app.domain.entities.rule_pack import RulePack
from app.domain.entities.decision import Decision, MatchedRuleTrace, RejectedRuleTrace
from app.domain.entities.manual_override import ManualOverride
from app.domain.entities.escalation import EscalationPolicy, EscalationLevel, EscalationEvent
from app.domain.entities.audit_log_entry import AuditLogEntry
from app.domain.entities.request_log_entry import RequestLogEntry
from app.domain.value_objects.rule_condition import RuleCondition


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _sample_rule(code="R-TEST-1"):
    return Rule(
        rule_code=code, name="Test rule", description="desc", family="NETWORK_IMPACT",
        family_order=2, priority_weight=50, severity_band="High", contribution_score=10,
        conditions=RuleCondition({"==": [{"var": "affectedUsers"}, 100]}),
        exceptions=None, conflict_group="priority", conflicts_with=[], is_suppressor=False,
        non_suppressible=False, cooldown_minutes=0, actions={"priority": "High"}, mitigations={},
    )


def test_rule_pack_save_get_activate_round_trip(session_factory):
    repo = PostgresRulePackRepository(session_factory)
    pack = RulePack(name="test-pack", version=1, status="draft", region=None, rules=[_sample_rule()])
    repo.save(pack)

    fetched = repo.get("test-pack", 1)
    assert fetched is not None
    assert fetched.name == "test-pack"
    assert len(fetched.rules) == 1
    assert fetched.rules[0].rule_code == "R-TEST-1"
    assert fetched.rules[0].conditions.is_satisfied_by({"affectedUsers": 100}) is True

    assert repo.get_active("test-pack") is None  # still draft
    activated = repo.activate("test-pack", 1)
    assert activated.status == "active"
    assert repo.get_active("test-pack").version == 1


def test_rule_pack_activate_deprecates_previous_active_version(session_factory):
    repo = PostgresRulePackRepository(session_factory)
    repo.save(RulePack(name="p", version=1, status="active", region=None, rules=[_sample_rule("R1")]))
    repo.save(RulePack(name="p", version=2, status="draft", region=None, rules=[_sample_rule("R2")]))

    repo.activate("p", 2)
    versions = {v.version: v.status for v in repo.list_versions("p")}
    assert versions == {1: "deprecated", 2: "active"}


def test_rule_repository_reads_the_active_pack(session_factory):
    pack_repo = PostgresRulePackRepository(session_factory)
    pack_repo.save(RulePack(name="noc-default", version=1, status="active", region=None, rules=[_sample_rule()]))

    rule_repo = PostgresRuleRepository(session_factory, rule_set_name="noc-default")
    active = rule_repo.get_active()
    assert active.name == "noc-default"
    assert len(active.rules) == 1


def test_rule_repository_raises_clear_error_when_nothing_seeded(session_factory):
    rule_repo = PostgresRuleRepository(session_factory, rule_set_name="noc-default")
    with pytest.raises(LookupError):
        rule_repo.get_active()


def test_decision_repository_append_only_history(session_factory):
    repo = PostgresDecisionRepository(session_factory)
    d1 = Decision(
        incident_id="INC-1", priority="High", risk_score=40, risk_band="MEDIUM",
        actions={"priority": "High"}, mitigations={}, execution_plan=[],
        matched_rules=[MatchedRuleTrace("R1", "n", "f", 10, "High", 5)],
        rejected_rules=[RejectedRuleTrace("R2", "n", "reason")],
        suppressed_rules=[], compliance_constraints=[], confidence_score=90.0,
        degraded_context=False, explanation="test",
    )
    d2 = Decision(
        incident_id="INC-1", priority="Critical", risk_score=80, risk_band="HIGH",
        actions={"priority": "Critical"}, mitigations={}, execution_plan=[],
        matched_rules=[], rejected_rules=[], suppressed_rules=[], compliance_constraints=[],
        confidence_score=95.0, degraded_context=False, explanation="test2",
    )
    repo.save(d1)
    repo.save(d2)

    history = repo.list_by_incident("INC-1")
    assert len(history) == 2
    assert history[0].explanation == "test"
    assert history[1].explanation == "test2"

    latest = repo.get("INC-1")
    assert latest.priority == "Critical"


def test_decision_repository_list_all_is_newest_first_and_paginates(session_factory):
    """Phase 4: DecisionRepository.list_all(), added for the decision-
    distribution analytics endpoint (GET /api/v1/decisions/distribution).
    Spans multiple incidents (unlike list_by_incident, which is scoped to
    one) -- newest-first, same ordering contract as
    InMemoryDecisionRepository.list_all()."""
    repo = PostgresDecisionRepository(session_factory)

    def _decision(incident_id, explanation, created_at):
        return Decision(
            incident_id=incident_id, priority="High", risk_score=40, risk_band="MEDIUM",
            actions={"priority": "High"}, mitigations={}, execution_plan=[],
            matched_rules=[], rejected_rules=[], suppressed_rules=[], compliance_constraints=[],
            confidence_score=90.0, degraded_context=False, explanation=explanation, created_at=created_at,
        )

    # Explicit, strictly-increasing timestamps -- real saves happen fast
    # enough in a tight loop that relying on datetime.now()'s default
    # would risk two rows landing in the same microsecond and making the
    # ORDER BY tie-break (and this test) nondeterministic.
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(5):
        repo.save(_decision(f"INC-LISTALL-{i}", f"decision {i}", base.replace(minute=i)))

    page1 = repo.list_all(limit=3, offset=0)
    assert [d.explanation for d in page1] == ["decision 4", "decision 3", "decision 2"]

    page2 = repo.list_all(limit=3, offset=3)
    assert [d.explanation for d in page2] == ["decision 1", "decision 0"]


def test_manual_override_round_trip(session_factory):
    repo = PostgresManualOverrideRepository(session_factory)
    override = ManualOverride(
        id="ov-1", decision_id="dec-1", operator="alice",
        original_decision={"priority": "High"}, override_decision={"priority": "Critical"},
        reason="VIP escalation", created_at=datetime.now(timezone.utc),
    )
    repo.save(override)
    fetched = repo.list_by_decision("dec-1")
    assert len(fetched) == 1
    assert fetched[0].operator == "alice"
    assert fetched[0].reason == "VIP escalation"


def test_escalation_policy_and_event_round_trip(session_factory):
    policy_repo = PostgresEscalationPolicyRepository(session_factory)
    engine = session_factory.kw["bind"]
    with sessionmaker(bind=engine)() as s:
        from app.infrastructure.db.mappers import escalation_policy_to_orm
        s.add(escalation_policy_to_orm(EscalationPolicy(
            severity_band="Critical",
            levels=[EscalationLevel("ENGINEER", 5), EscalationLevel("NATIONAL_NOC", 30)],
        )))
        s.commit()

    fetched_policy = policy_repo.get_for_severity("Critical")
    assert fetched_policy is not None
    assert [lvl.level for lvl in fetched_policy.levels] == ["ENGINEER", "NATIONAL_NOC"]
    assert policy_repo.get_for_severity("NotABand") is None

    event_repo = PostgresEscalationRepository(session_factory)
    event = EscalationEvent(id="e1", decision_id="dec-1", level="ENGINEER", triggered_at=datetime.now(timezone.utc))
    event_repo.save(event)
    events = event_repo.list_by_decision("dec-1")
    assert len(events) == 1
    assert events[0].level == "ENGINEER"


def test_audit_log_round_trip(session_factory):
    repo = PostgresAuditLogRepository(session_factory)
    entry = AuditLogEntry(
        id="a1", entity_type="rule", entity_id="R001", action="updated", actor="bob",
        before={"priority_weight": 50}, after={"priority_weight": 60},
        ip_address="10.0.0.1", request_id="req-1", correlation_id="corr-1",
        created_at=datetime.now(timezone.utc),
    )
    repo.save(entry)
    fetched = repo.list_by_entity("rule", "R001")
    assert len(fetched) == 1
    assert fetched[0].actor == "bob"
    assert fetched[0].after["priority_weight"] == 60


def test_request_log_save(session_factory):
    repo = PostgresRequestLogRepository(session_factory)
    entry = RequestLogEntry(
        id="rl-1", method="POST", path="/api/v1/incidents/evaluate", status_code=200,
        duration_ms=12.5, request_id="req-1", correlation_id=None, ip_address="127.0.0.1",
        created_at=datetime.now(timezone.utc),
    )
    saved = repo.save(entry)
    assert saved.status_code == 200


# -- Phase 2: auth repositories -------------------------------------------

from app.infrastructure.repositories.postgres_user_repository import PostgresUserRepository
from app.infrastructure.repositories.postgres_role_repository import PostgresRoleRepository
from app.infrastructure.repositories.postgres_permission_repository import PostgresPermissionRepository
from app.infrastructure.repositories.postgres_api_key_repository import PostgresAPIKeyRepository
from app.domain.entities.user import User
from app.domain.entities.role import Role
from app.domain.entities.permission import Permission
from app.domain.entities.api_key import APIKey
import uuid as _uuid


def test_postgres_user_repository_round_trip(session_factory):
    repo = PostgresUserRepository(session_factory)
    user = User(id=str(_uuid.uuid4()), email="Test@Example.com", hashed_password="hashed", full_name="Test User", roles=["viewer"])
    saved = repo.save(user)
    assert saved.id == user.id

    by_id = repo.get_by_id(user.id)
    assert by_id is not None and by_id.email == "Test@Example.com"

    # Email lookup is case-insensitive, matching InMemoryUserRepository.
    by_email = repo.get_by_email("test@example.com")
    assert by_email is not None and by_email.id == user.id

    assert repo.get_by_email("nobody@example.com") is None
    assert len(repo.list_all()) == 1

    saved.full_name = "Updated Name"
    repo.save(saved)
    assert repo.get_by_id(user.id).full_name == "Updated Name"


def test_postgres_role_repository_round_trip(session_factory):
    repo = PostgresRoleRepository(session_factory)
    role = Role(code="operator", name="Operator", permissions=["incidents:evaluate"])
    repo.save(role)

    fetched = repo.get_by_code("operator")
    assert fetched is not None and fetched.permissions == ["incidents:evaluate"]

    # Saving again with the same code updates in place (upsert semantics).
    role.permissions = ["incidents:evaluate", "decisions:read"]
    repo.save(role)
    assert repo.get_by_code("operator").permissions == ["incidents:evaluate", "decisions:read"]
    assert len(repo.list_all()) == 1


def test_postgres_permission_repository_round_trip(session_factory):
    repo = PostgresPermissionRepository(session_factory)
    repo.save(Permission(code="rules:manage", description="Manage rule packs"))
    fetched = repo.get_by_code("rules:manage")
    assert fetched is not None and fetched.description == "Manage rule packs"
    assert repo.get_by_code("does:not-exist") is None


def test_postgres_api_key_repository_round_trip(session_factory):
    repo = PostgresAPIKeyRepository(session_factory)
    key = APIKey(id=str(_uuid.uuid4()), key_prefix="tdo_abc123", hashed_key="hashed", name="ci key", roles=["operator"])
    repo.save(key)

    fetched = repo.get_by_prefix("tdo_abc123")
    assert fetched is not None and fetched.is_active is True

    revoked = repo.revoke(key.id)
    assert revoked.is_active is False
    assert repo.get_by_id(key.id).is_active is False


# -- Phase 2.5: incident repository ---------------------------------------

from app.infrastructure.repositories.postgres_incident_repository import PostgresIncidentRepository
from app.domain.entities.incident import Incident


def test_postgres_incident_repository_round_trip(session_factory):
    repo = PostgresIncidentRepository(session_factory)
    incident = Incident(incident_id="INC-PG-1", payload={"towerId": "T-1"}, region="Delhi")
    repo.save(incident)

    fetched = repo.get("INC-PG-1")
    assert fetched is not None and fetched.payload == {"towerId": "T-1"} and fetched.status == "received"

    fetched.status = "evaluated"
    repo.save(fetched)
    assert repo.get("INC-PG-1").status == "evaluated"

    all_received = repo.list_all(status="received")
    assert all_received == []
    all_evaluated = repo.list_all(status="evaluated")
    assert len(all_evaluated) == 1
