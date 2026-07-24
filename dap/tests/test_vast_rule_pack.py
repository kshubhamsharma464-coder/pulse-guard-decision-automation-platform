"""Tests for vast_rule_pack_loader.py -- the adapter that transpiles
customer_sla_rules_vast.json's 30 CSR-xxx generic customer-request-workflow
rules into native Rule entities, all sharing one new family
(CUSTOMER_REQUEST_WORKFLOW) and one conflict_group (customer-decision)."""

from app.infrastructure.repositories.vast_rule_pack_loader import load_vast_rules


def test_loads_thirty_rules_all_in_one_family_and_conflict_group():
    rules = load_vast_rules()
    assert len(rules) == 30
    assert all(r.family == "CUSTOMER_REQUEST_WORKFLOW" for r in rules)
    assert all(r.conflict_group == "customer-decision" for r in rules)


def test_csr_021_priority_override_breaks_tie_with_csr_001():
    """Deliberate, documented override: CSR-021 (fraud block) bumped from
    priority 100 to 105 so it deterministically beats CSR-001 (enterprise
    approve) rather than losing on alphabetical rule_code tiebreak."""
    rules = {r.rule_code: r for r in load_vast_rules()}
    assert rules["CSR-021"].priority_weight == 105
    assert rules["CSR-001"].priority_weight == 100


def test_nested_dotted_field_lookup():
    rules = {r.rule_code: r for r in load_vast_rules()}
    r = rules["CSR-001"]
    assert r.conditions.is_satisfied_by({"customer": {"segment": "enterprise"}}) is True
    assert r.conditions.is_satisfied_by({"customer": {"segment": "consumer"}}) is False


def test_any_logic_matches_on_either_disjunct():
    rules = {r.rule_code: r for r in load_vast_rules()}
    r = rules["CSR-007"]
    assert r.conditions.is_satisfied_by({"request": {"submitted_hour": 20}}) is True
    assert r.conditions.is_satisfied_by({"request": {"submitted_hour": 12}}) is False


def test_contains_operator_on_tags_list():
    rules = {r.rule_code: r for r in load_vast_rules()}
    r = rules["CSR-020"]
    assert r.conditions.is_satisfied_by({"customer": {"tags": ["vip", "loyal"]}}) is True
    assert r.conditions.is_satisfied_by({"customer": {"tags": ["loyal"]}}) is False


def test_action_fields_are_namespaced_to_avoid_collision():
    rules = load_vast_rules()
    for r in rules:
        assert set(r.actions.keys()) == {"customerDecision", "customerAction"}
