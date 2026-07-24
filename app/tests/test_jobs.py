from datetime import datetime, timedelta, timezone
from app.domain.entities.decision import Decision
from app.domain.entities.escalation import EscalationPolicy, EscalationLevel
from app.jobs.sla_breach_sweep import SlaBreachSweep
from app.jobs.escalation_sweep import EscalationSweep


def _decision(created_minutes_ago, target_sla="15 minutes", priority="Critical", resolved=False):
    return Decision(
        incident_id="INC-SLA", priority=priority, risk_score=90, risk_band="CRITICAL",
        actions={"priority": priority, "targetSLA": target_sla}, mitigations={}, execution_plan=[],
        matched_rules=[], rejected_rules=[], suppressed_rules=[], compliance_constraints=[],
        confidence_score=100.0, degraded_context=False, explanation="test",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=created_minutes_ago),
        resolved=resolved,
    )


def test_sla_sweep_bumps_priority_past_80_percent_elapsed():
    decision = _decision(created_minutes_ago=13, target_sla="15 minutes", priority="High")  # 13/15 = 86.7%
    bumped = SlaBreachSweep(threshold_fraction=0.8).run([decision])
    assert bumped == ["INC-SLA"]
    assert decision.priority == "Critical"


def test_sla_sweep_does_not_bump_beyond_critical():
    decision = _decision(created_minutes_ago=13, target_sla="15 minutes", priority="Critical")
    bumped = SlaBreachSweep(threshold_fraction=0.8).run([decision])
    assert bumped == []  # already at the top band -- nothing to bump to
    assert decision.priority == "Critical"


def test_sla_sweep_does_not_bump_when_well_within_target():
    decision = _decision(created_minutes_ago=2, target_sla="15 minutes")
    bumped = SlaBreachSweep(threshold_fraction=0.8).run([decision])
    assert bumped == []


def test_sla_sweep_skips_resolved_decisions():
    decision = _decision(created_minutes_ago=20, target_sla="15 minutes", resolved=True)
    bumped = SlaBreachSweep(threshold_fraction=0.8).run([decision])
    assert bumped == []


def test_sla_sweep_bumps_medium_to_high():
    decision = _decision(created_minutes_ago=13, target_sla="15 minutes", priority="Medium")
    bumped = SlaBreachSweep(threshold_fraction=0.8).run([decision])
    assert bumped == ["INC-SLA"]
    assert decision.priority == "High"
    assert decision.actions["supervisorNotified"] is True


def test_escalation_sweep_opens_the_furthest_crossed_level():
    policy = EscalationPolicy(severity_band="Critical", levels=[
        EscalationLevel("ENGINEER", 5),
        EscalationLevel("REGIONAL_MANAGER", 15),
        EscalationLevel("NATIONAL_NOC", 30),
    ])
    created_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    event = EscalationSweep().run("INC-ESC", policy, existing_events=[], decision_created_at=created_at)
    assert event is not None
    assert event.level == "REGIONAL_MANAGER"  # 20 min elapsed: past ENGINEER(5) and REGIONAL_MANAGER(15), not NATIONAL_NOC(30)


def test_escalation_sweep_does_not_retrigger_an_already_opened_level():
    from app.domain.entities.escalation import EscalationEvent
    policy = EscalationPolicy(severity_band="Critical", levels=[EscalationLevel("ENGINEER", 5)])
    created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    existing = [EscalationEvent(id="e1", decision_id="INC-ESC", level="ENGINEER", triggered_at=created_at)]
    event = EscalationSweep().run("INC-ESC", policy, existing_events=existing, decision_created_at=created_at)
    assert event is None


def test_escalation_policy_repository_has_real_seeded_data_for_all_bands():
    """Before this, EscalationPolicy/EscalationEvent and EscalationSweep
    existed but no concrete policy data was ever seeded anywhere -- the
    sweep always had nothing to walk. This proves the previously-unfed job
    is now genuinely usable end to end for every severity band the rest of
    the system produces."""
    from app.infrastructure.repositories.in_memory_escalation_policy_repository import InMemoryEscalationPolicyRepository

    repo = InMemoryEscalationPolicyRepository()
    for band in ("Critical", "High", "Medium", "Low"):
        policy = repo.get_for_severity(band)
        assert policy is not None
        assert policy.severity_band == band
        assert len(policy.levels) >= 1
        # timeouts must be strictly increasing so EscalationSweep's
        # furthest-crossed-level logic behaves sensibly
        timeouts = [lvl.timeout_minutes for lvl in policy.levels]
        assert timeouts == sorted(timeouts) and len(set(timeouts)) == len(timeouts)


def test_escalation_sweep_runs_end_to_end_against_seeded_critical_policy():
    from app.infrastructure.repositories.in_memory_escalation_policy_repository import InMemoryEscalationPolicyRepository

    policy = InMemoryEscalationPolicyRepository().get_for_severity("Critical")
    created_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    event = EscalationSweep().run("INC-SEEDED", policy, existing_events=[], decision_created_at=created_at)
    assert event is not None
    # Critical policy: ENGINEER@5, REGIONAL_MANAGER@15, NATIONAL_NOC@30 -- 20 min elapsed lands on REGIONAL_MANAGER
    assert event.level == "REGIONAL_MANAGER"


def test_escalation_policy_repository_returns_none_for_unknown_band():
    from app.infrastructure.repositories.in_memory_escalation_policy_repository import InMemoryEscalationPolicyRepository
    assert InMemoryEscalationPolicyRepository().get_for_severity("NotABand") is None
