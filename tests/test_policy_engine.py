from app.domain.entities.incident import Incident


def test_inc_101_matches_expected_rules(use_case, inc_101_payload):
    """Exact problem-statement example. affectedUsers=15000 (>10000, R001), VIP (R007),
    Gold SLA (R004) -- and, run for real rather than hand-traced, networkLoad=94 (>90,
    R012) and historicalFailures=4 (>3, R009) also legitimately match. The earlier
    hand-written walkthrough in decision-engine-design.md missed R012/R009 -- this
    test is the correction."""
    incident = Incident(incident_id=inc_101_payload["incidentId"], payload=inc_101_payload)
    decision = use_case.execute(incident)

    matched_codes = {r.rule_code for r in decision.matched_rules}
    assert matched_codes == {"R001", "R004", "R007", "R009", "R012"}

    assert decision.priority == "Critical"
    assert decision.actions["targetSLA"] == "15 minutes"
    assert decision.actions["dispatchEngineer"] is True
    assert decision.actions["rerouteTraffic"] is True          # from R012, not R001 alone
    assert decision.actions["notifyAccountManager"] is True     # from R007
    assert decision.actions["flagForInfrastructureReview"] is True  # from R009
    assert decision.suppressed_rules == []
    assert decision.risk_score > 0


def test_missing_fields_do_not_crash_and_rule_conditions_simply_evaluate_false(use_case):
    """Design doc edge case #3: a rule referencing an absent field evaluates false,
    not an error -- EXCEPT R006, whose second disjunct ({"==": [{"var": "slaTier"},
    null]}) is deliberately written to treat a *missing* SLA tier as Bronze-tier
    default. On a fully empty incident that's the one rule that's supposed to match;
    everything else correctly doesn't."""
    incident = Incident(incident_id="INC-EMPTY", payload={})
    decision = use_case.execute(incident)
    matched_codes = {r.rule_code for r in decision.matched_rules}
    assert matched_codes == {"R006"}
    assert decision.actions.get("targetSLA") == "4 hours"
    assert decision.priority is None  # R006 only sets targetSLA, not priority


def test_emergency_services_forces_critical_regardless_of_scale(use_case):
    incident = Incident(incident_id="INC-EMERGENCY", payload={
        "emergencyServicesAffected": True,
        "affectedUsers": 12,
    })
    decision = use_case.execute(incident)
    assert decision.priority == "Critical"
    assert any(r.rule_code == "R008" for r in decision.matched_rules)
