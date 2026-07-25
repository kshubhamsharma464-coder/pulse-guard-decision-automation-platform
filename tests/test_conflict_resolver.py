from app.domain.entities.incident import Incident


def test_maintenance_window_suppresses_dispatch(use_case):
    """R011 (suppressor) should win over R001/R002-style dispatch when nothing
    non-suppressible also matched."""
    incident = Incident(incident_id="INC-MAINT", payload={
        "affectedUsers": 5000,
        "maintenanceWindow": True,
    })
    decision = use_case.execute(incident)
    assert decision.actions["dispatchEngineer"] is False
    assert decision.actions.get("autoCloseAsExpected") is True
    suppressed_codes = {s["rule_code"] for s in decision.suppressed_rules}
    assert "R011" not in suppressed_codes  # R011 is the winner here, not suppressed


def test_non_suppressible_rule_overrides_maintenance_suppressor(use_case):
    """Design doc §3b step 3: emergency services (non_suppressible=True) must win
    dispatchEngineer even though a maintenance window also matched."""
    incident = Incident(incident_id="INC-EMERGENCY-MAINT", payload={
        "emergencyServicesAffected": True,
        "maintenanceWindow": True,
    })
    decision = use_case.execute(incident)
    assert decision.actions["dispatchEngineer"] is True
    assert decision.priority == "Critical"

    suppressed_codes = {s["rule_code"] for s in decision.suppressed_rules}
    assert "R011" in suppressed_codes  # the suppressor was the one that got overridden
