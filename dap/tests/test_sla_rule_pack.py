"""Tests for sla_rule_pack_loader.py -- the adapter that transpiles
customer_sla_rules_telecom.json (8 SLA-RULE-xxx source rules) into 12 native
Rule entities, plus the SlaMatrixLookup fill-in step wired into the
orchestrator."""

from app.infrastructure.repositories.sla_rule_pack_loader import load_sla_rules, load_sla_matrix
from app.domain.services.sla_matrix_lookup import SlaMatrixLookup


def test_loads_twelve_rules_from_eight_source_rules():
    """SLA-RULE-002's weightTable (Platinum/Gold/Silver/Bronze/Residential)
    expands into 5 separate internal rules; the other 7 source rules map 1:1."""
    rules = load_sla_rules()
    assert len(rules) == 12
    codes = {r.rule_code for r in rules}
    assert "SLA-RULE-008" in codes
    assert {"SLA-RULE-002-PLATINUM", "SLA-RULE-002-GOLD", "SLA-RULE-002-SILVER",
            "SLA-RULE-002-BRONZE", "SLA-RULE-002-RESIDENTIAL"}.issubset(codes)


def test_emergency_rule_is_non_suppressible_and_bypasses_additive_scoring():
    rules = {r.rule_code: r for r in load_sla_rules()}
    r = rules["SLA-RULE-008"]
    assert r.non_suppressible is True
    assert r.contribution_score is None
    assert r.family == "SAFETY_REGULATORY"
    data = {"isEmergencyServiceLine": True}
    assert r.conditions.is_satisfied_by(data) is True


def test_platinum_tier_critical_bypasses_additive_scoring():
    rules = {r.rule_code: r for r in load_sla_rules()}
    r = rules["SLA-RULE-001"]
    assert r.contribution_score is None
    assert r.actions["priority"] == "Critical"


def test_dynamic_threshold_formula_uses_multiply_operator():
    rules = {r.rule_code: r for r in load_sla_rules()}
    r = rules["SLA-RULE-004"]
    assert r.conditions.is_satisfied_by({"minutesSinceIncidentOpened": 45, "slaResponseMinutes": 50}) is True
    assert r.conditions.is_satisfied_by({"minutesSinceIncidentOpened": 30, "slaResponseMinutes": 50}) is False
    assert r.actions["priorityBumpOneLevel"] is True
    assert r.actions["slaBreachImminent"] is True


def test_maintenance_suppression_uses_not_equals_for_platinum_exclusion():
    rules = {r.rule_code: r for r in load_sla_rules()}
    r = rules["SLA-RULE-007"]
    assert r.is_suppressor is True
    assert r.conflict_group == "dispatch-suppression"
    data_platinum = {"isDuringPlannedMaintenance": True, "customerTier": "PLATINUM"}
    data_gold = {"isDuringPlannedMaintenance": True, "customerTier": "GOLD"}
    assert r.conditions.is_satisfied_by(data_platinum) is False
    assert r.conditions.is_satisfied_by(data_gold) is True


def test_sla_matrix_lookup_resolves_tier_and_priority_to_response_targets():
    matrix = load_sla_matrix()
    lookup = SlaMatrixLookup(matrix)
    result = lookup.resolve("Gold", "Critical")
    assert result is not None
    assert "responseMinutes" in result and "resolutionMinutes" in result


def test_sla_matrix_lookup_returns_none_for_unknown_tier_or_priority():
    matrix = load_sla_matrix()
    lookup = SlaMatrixLookup(matrix)
    assert lookup.resolve(None, "Critical") is None
    assert lookup.resolve("Gold", None) is None
    assert lookup.resolve("NotATier", "Critical") is None
