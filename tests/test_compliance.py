from app.domain.entities.incident import Incident


def test_government_segment_applies_reroute_constraint(use_case):
    """Design doc §6.5 -- COMPLIANCE rules run after conflict resolution and narrow
    execution without competing for priority."""
    incident = Incident(
        incident_id="INC-GOV",
        payload={"affectedUsers": 20000},
        enriched_context={"customerSegment": "Government"},
    )
    decision = use_case.execute(incident)
    assert decision.actions["rerouteTrafficConstraint"] == "in-region-only"
    assert decision.actions["publicInternetFailoverAllowed"] is False
    assert any(c["rule_code"] == "R030" for c in decision.compliance_constraints)
    # compliance rules never contend for priority
    assert not any(m.rule_code == "R030" for m in decision.matched_rules)


def test_no_compliance_constraints_for_ordinary_customer(use_case):
    incident = Incident(incident_id="INC-ORD", payload={"affectedUsers": 20000})
    decision = use_case.execute(incident)
    assert decision.compliance_constraints == []
    assert "rerouteTrafficConstraint" not in decision.actions
