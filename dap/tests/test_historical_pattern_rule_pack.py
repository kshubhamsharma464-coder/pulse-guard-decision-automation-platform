"""Tests for historical_pattern_rule_pack_loader.py -- the adapter that
transpiles telecom_incident_decision_engine_rules.json's 30 HIS-xxx rules
into native Rule entities. Covers the "incident."-prefix stripping (same
convention as the CSR-SLA pack), the untouched nested-namespace paths
(asset./metrics./customer./change./context., same convention as the vast
pack), var-to-var comparison, the his*-namespaced action fields (and why
that namespace choice matters given ConflictResolver's global per-field
grouping), and the shared conflict_group's weight-based tiebreak."""

from app.infrastructure.repositories.historical_pattern_rule_pack_loader import load_historical_pattern_rules


def test_loads_thirty_rules_in_one_family_and_conflict_group():
    rules = load_historical_pattern_rules()
    assert len(rules) == 30
    assert all(r.family == "HISTORICAL_OPERATIONAL_PATTERN" for r in rules)
    assert all(r.conflict_group == "his-decision" for r in rules)
    assert all(r.contribution_score is None for r in rules)


def test_incident_prefix_is_stripped_but_other_namespaces_are_not():
    rules = {r.rule_code: r for r in load_historical_pattern_rules()}
    r = rules["HIS002"]
    # "incident.relatedChangeStatus"/"incident.affectedAsset" -> stripped to
    # top-level; "change.assetId"/"change.result" -> left nested.
    data = {"relatedChangeStatus": "FAILED", "affectedAsset": "NODE-1",
            "change": {"assetId": "NODE-1", "result": "rollback"}}
    assert r.conditions.is_satisfied_by(data) is True
    assert r.conditions.is_satisfied_by(dict(data, affectedAsset="NODE-2")) is False


def test_asset_and_context_namespaces_resolve_as_nested_dotted_paths():
    rules = {r.rule_code: r for r in load_historical_pattern_rules()}
    r1 = rules["HIS001"]
    assert r1.conditions.is_satisfied_by({"asset": {"rebootCount7d": 4, "rebootCount30d": 6}}) is True
    assert r1.conditions.is_satisfied_by({"asset": {"rebootCount7d": 1, "rebootCount30d": 6}}) is False

    r11 = rules["HIS011"]
    assert r11.conditions.is_satisfied_by({"context": {"weatherSeverity": "severe", "month": "jul"}}) is True
    assert r11.conditions.is_satisfied_by({"context": {"weatherSeverity": "mild", "month": "jul"}}) is False


def test_action_fields_are_his_namespaced_to_avoid_global_field_collision():
    """Not a defensive nicety -- ConflictResolver groups writers by field
    name across ALL matched rules regardless of pack/conflict_group, so a
    bare "decision" or "priority" key here would silently interact with the
    CSR-SLA pack's "decision" field or the base pack's categorical
    Critical/High/Medium/Low "priority" field."""
    rules = load_historical_pattern_rules()
    expected_keys = {"hisDecision", "hisPriority", "hisConfidence", "hisAssignmentGroup",
                      "hisEscalationLevel", "hisReasonCodes", "hisSlaBreachRisk"}
    for r in rules:
        assert set(r.actions.keys()) == expected_keys
    all_keys = {k for r in rules for k in r.actions}
    assert "decision" not in all_keys
    assert "priority" not in all_keys


def test_priority_weight_preserves_source_priority_for_conflict_tiebreak():
    rules = {r.rule_code: r for r in load_historical_pattern_rules()}
    assert rules["HIS015"].priority_weight == 985  # highest in the pack
    assert rules["HIS014"].priority_weight == 895  # lowest in the pack


def test_rule_codes_do_not_collide_with_any_other_pack():
    from app.infrastructure.repositories.in_memory_rule_repository import InMemoryRuleRepository
    from app.infrastructure.repositories.sla_rule_pack_loader import load_sla_rules
    from app.infrastructure.repositories.vast_rule_pack_loader import load_vast_rules
    from app.infrastructure.repositories.csr_sla_rule_pack_loader import load_csr_sla_rules

    base_codes = {r.rule_code for r in InMemoryRuleRepository().get_active().rules}
    other_codes = (
        {r.rule_code for r in load_sla_rules()}
        | {r.rule_code for r in load_vast_rules()}
        | {r.rule_code for r in load_csr_sla_rules()}
    )
    his_codes = {r.rule_code for r in load_historical_pattern_rules()}
    assert not (base_codes & his_codes)
    assert not (other_codes & his_codes)
