"""Tests for net_inf_rule_pack_loader.py -- the adapter for
telecom_network_infrastructure_rules.json's 20 NET-INF-xxx rules. This pack
is different from every other merged pack: it is NOT purely additive at the
source-rule level. Six of its 20 rules are functional duplicates of
existing CSR-SLA rules and are deliberately skipped at load time (see
SKIPPED_RULE_IDS in the loader). These tests pin down both the skip
decision and the deliberate cross-pack policy disagreement that was kept
(NET-INF-010 vs CSR-SLA-013)."""

from app.infrastructure.repositories.net_inf_rule_pack_loader import load_net_inf_rules, SKIPPED_RULE_IDS
from app.infrastructure.repositories.csr_sla_rule_pack_loader import load_csr_sla_rules


def test_loads_fourteen_of_twenty_source_rules():
    rules = load_net_inf_rules()
    assert len(rules) == 14
    codes = {r.rule_code for r in rules}
    assert not (codes & set(SKIPPED_RULE_IDS.keys()))


def test_skipped_rules_are_exactly_the_six_documented_duplicates():
    assert set(SKIPPED_RULE_IDS.keys()) == {
        "NET-INF-003", "NET-INF-004", "NET-INF-005",
        "NET-INF-006", "NET-INF-009", "NET-INF-011",
    }


def test_all_in_one_family_and_conflict_group_with_no_additive_score():
    rules = load_net_inf_rules()
    assert all(r.family == "NETWORK_INFRASTRUCTURE_PATTERN" for r in rules)
    assert all(r.conflict_group == "net-inf-decision" for r in rules)
    assert all(r.contribution_score is None for r in rules)


def test_action_fields_are_net_inf_namespaced_to_avoid_csr_sla_collision():
    """CSR-SLA already writes bare "decision"/"escalationTarget". If NET-INF
    also wrote those bare, ConflictResolver's global per-field grouping
    would let one pack's routing recommendation silently overwrite the
    other's -- exactly what NET-INF-010 vs CSR-SLA-013 (same condition,
    different intended escalationTarget) would trigger."""
    rules = load_net_inf_rules()
    expected_keys = {"netInfDecision", "netInfAction", "netInfEscalationTarget",
                      "netInfPriorityScore", "netInfConfidence", "netInfExplanation"}
    for r in rules:
        assert set(r.actions.keys()) == expected_keys
    all_keys = {k for r in rules for k in r.actions}
    csr_sla_keys = {k for r in load_csr_sla_rules() for k in r.actions}
    assert not (all_keys & csr_sla_keys)


def test_net_inf_002_is_a_stricter_superset_of_csr_sla_005_not_a_duplicate():
    """NET-INF-002 adds an extra mtbfHours<=72 condition on top of
    CSR-SLA-005's tower-failure condition and routes to ran_engineering
    instead of engineering_oncall -- kept because it's a genuinely more
    specific companion rule, not redundant."""
    rules = {r.rule_code: r for r in load_net_inf_rules()}
    r = rules["NET-INF-002"]
    base_match = {"assetType": "tower", "failuresSameAsset7d": 4, "failuresSameAsset30d": 6}
    assert r.conditions.is_satisfied_by(dict(base_match, mtbfHours=50)) is True
    assert r.conditions.is_satisfied_by(dict(base_match, mtbfHours=100)) is False
    assert r.actions["netInfEscalationTarget"] == "ran_engineering"


def test_incident_prefix_is_stripped():
    rules = {r.rule_code: r for r in load_net_inf_rules()}
    r = rules["NET-INF-001"]
    data = {"networkLayer": "core", "severity": "critical", "serviceImpact": True}
    assert r.conditions.is_satisfied_by(data) is True


def test_rule_codes_do_not_collide_with_any_other_pack():
    from app.infrastructure.repositories.in_memory_rule_repository import InMemoryRuleRepository
    from app.infrastructure.repositories.sla_rule_pack_loader import load_sla_rules
    from app.infrastructure.repositories.vast_rule_pack_loader import load_vast_rules
    from app.infrastructure.repositories.historical_pattern_rule_pack_loader import load_historical_pattern_rules

    base_codes = {r.rule_code for r in InMemoryRuleRepository().get_active().rules}
    other_codes = (
        {r.rule_code for r in load_sla_rules()}
        | {r.rule_code for r in load_vast_rules()}
        | {r.rule_code for r in load_csr_sla_rules()}
        | {r.rule_code for r in load_historical_pattern_rules()}
    )
    net_inf_codes = {r.rule_code for r in load_net_inf_rules()}
    assert not (base_codes & net_inf_codes)
    assert not (other_codes & net_inf_codes)
