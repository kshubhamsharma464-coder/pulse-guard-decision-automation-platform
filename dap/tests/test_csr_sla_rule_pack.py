"""Tests for csr_sla_rule_pack_loader.py -- the adapter that transpiles
csr_sla_decision_rules.json's 18 CSR-SLA-xxx rules (ruleSetId
"telecom-customer-sla-rules") into native Rule entities. Covers the
"incident."-prefix stripping, the shared conflict_group's weight-based
tiebreak (mirroring the source pack's own declared
highest_priority_then_highest_confidence_then_newest_version policy, using
weight as the primary criterion), var-to-var field comparison, and the
csrSla*-namespaced action fields."""

from app.infrastructure.repositories.csr_sla_rule_pack_loader import load_csr_sla_rules


def test_loads_eighteen_rules_in_one_family_and_conflict_group():
    rules = load_csr_sla_rules()
    assert len(rules) == 18
    assert all(r.family == "CUSTOMER_SLA_PRIORITY" for r in rules)
    assert all(r.conflict_group == "csr-sla-priority-decision" for r in rules)
    assert all(r.contribution_score is None for r in rules)


def test_incident_prefix_is_stripped_so_conditions_match_flat_payload_fields():
    rules = {r.rule_code: r for r in load_csr_sla_rules()}
    r = rules["CSR-SLA-004"]
    assert r.conditions.is_satisfied_by({"slaBreached": True, "isClosed": False}) is True
    assert r.conditions.is_satisfied_by({"slaBreached": False, "isClosed": False}) is False


def test_var_to_var_comparison_for_service_id_match():
    rules = {r.rule_code: r for r in load_csr_sla_rules()}
    r = rules["CSR-SLA-007"]
    same_service = {
        "similarIncidentExists": True, "similarIncidentAgeMinutes": 10,
        "similarIncidentServiceId": "SVC-1", "serviceId": "SVC-1",
    }
    diff_service = dict(same_service, serviceId="SVC-2")
    assert r.conditions.is_satisfied_by(same_service) is True
    assert r.conditions.is_satisfied_by(diff_service) is False


def test_action_fields_are_namespaced_to_avoid_collision():
    rules = load_csr_sla_rules()
    expected_keys = {"decision", "csrSlaAction", "escalationTarget",
                      "csrSlaPriorityScore", "csrSlaConfidence", "csrSlaExplanation"}
    for r in rules:
        assert set(r.actions.keys()) == expected_keys


def test_priority_weight_preserves_source_priority_for_conflict_tiebreak():
    rules = {r.rule_code: r for r in load_csr_sla_rules()}
    assert rules["CSR-SLA-018"].priority_weight == 960
    assert rules["CSR-SLA-016"].priority_weight == 300


def test_rule_codes_do_not_collide_with_base_sla_or_vast_packs():
    from app.infrastructure.repositories.in_memory_rule_repository import InMemoryRuleRepository
    from app.infrastructure.repositories.sla_rule_pack_loader import load_sla_rules
    from app.infrastructure.repositories.vast_rule_pack_loader import load_vast_rules

    base_codes = {r.rule_code for r in InMemoryRuleRepository().get_active().rules}
    sla_codes = {r.rule_code for r in load_sla_rules()}
    vast_codes = {r.rule_code for r in load_vast_rules()}
    csr_sla_codes = {r.rule_code for r in load_csr_sla_rules()}

    assert not (base_codes & csr_sla_codes)
    assert not (sla_codes & csr_sla_codes)
    assert not (vast_codes & csr_sla_codes)
