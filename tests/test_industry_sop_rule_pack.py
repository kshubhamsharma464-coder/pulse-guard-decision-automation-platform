"""Tests for industry_sop_rule_pack_loader.py -- the three rules closing
genuine gaps found by auditing the existing rule base against real telecom
NOC/ITIL SOPs (vendor UPC escalation, change-freeze governance, mass-outage
regulatory reporting threshold). Also proves the audit's core claim: these
rules reuse base-pack action fields that existed but were never triggered
(escalateVendor, regulatoryReportingRequired/DeadlineHours), and that doing
so is safe because their condition fields are new and can't match any
existing test payload."""

from app.infrastructure.repositories.industry_sop_rule_pack_loader import load_industry_sop_rules
from app.infrastructure.repositories.in_memory_rule_repository import InMemoryRuleRepository


def test_loads_three_rules_slotted_into_existing_base_pack_families():
    rules = {r.rule_code: r for r in load_industry_sop_rules()}
    assert set(rules.keys()) == {"SOP-VEN-001", "SOP-CHG-001", "SOP-REG-001"}
    assert rules["SOP-VEN-001"].family == "OPERATIONAL_FEASIBILITY"
    assert rules["SOP-CHG-001"].family == "TEMPORAL"
    assert rules["SOP-REG-001"].family == "SAFETY_REGULATORY"


def test_vendor_escalation_reuses_previously_unset_base_pack_field():
    """escalateVendor was declared in rules-seed.json's action-field
    vocabulary but grep confirmed no rule ever set it True before this one --
    pinned here since the claim matters to the "already covered?" audit."""
    base_rules = InMemoryRuleRepository().get_active().rules
    assert not any(r.actions.get("escalateVendor") for r in base_rules)

    rules = {r.rule_code: r for r in load_industry_sop_rules()}
    r = rules["SOP-VEN-001"]
    assert r.conditions.is_satisfied_by({"rootCauseVendorAttributed": True, "vendorContractHasUpc": True}) is True
    assert r.conditions.is_satisfied_by({"rootCauseVendorAttributed": True, "vendorContractHasUpc": False}) is False
    assert r.actions["escalateVendor"] is True
    assert r.actions["vendorResponseDeadlineMinutes"] == 60


def test_change_freeze_violation_requires_no_emergency_approval():
    rules = {r.rule_code: r for r in load_industry_sop_rules()}
    r = rules["SOP-CHG-001"]
    base = {"changeFreezeActive": True, "changeLinkedToIncident": True}
    assert r.conditions.is_satisfied_by(dict(base, changeEmergencyApproved=False)) is True
    assert r.conditions.is_satisfied_by(dict(base, changeEmergencyApproved=True)) is False
    assert r.actions["priorityFloor"] == "High"


def test_mass_outage_regulatory_threshold_uses_multiply_operator():
    rules = {r.rule_code: r for r in load_industry_sop_rules()}
    r = rules["SOP-REG-001"]
    # 20,000 users x 60 minutes = 1,200,000 user-minutes >= 900,000 threshold
    assert r.conditions.is_satisfied_by({"affectedUsers": 20000, "outageDurationMinutes": 60, "serviceImpact": True}) is True
    # 1,000 x 60 = 60,000 -- well under threshold
    assert r.conditions.is_satisfied_by({"affectedUsers": 1000, "outageDurationMinutes": 60, "serviceImpact": True}) is False
    assert r.actions["regulatoryReportingRequired"] is True
    assert r.actions["regulatoryReportingDeadlineHours"] == 24
    assert r.non_suppressible is True


def test_rule_codes_do_not_collide_with_any_other_pack():
    from app.infrastructure.repositories.sla_rule_pack_loader import load_sla_rules
    from app.infrastructure.repositories.vast_rule_pack_loader import load_vast_rules
    from app.infrastructure.repositories.csr_sla_rule_pack_loader import load_csr_sla_rules
    from app.infrastructure.repositories.historical_pattern_rule_pack_loader import load_historical_pattern_rules
    from app.infrastructure.repositories.net_inf_rule_pack_loader import load_net_inf_rules

    base_codes = {r.rule_code for r in InMemoryRuleRepository().get_active().rules}
    other_codes = (
        {r.rule_code for r in load_sla_rules()}
        | {r.rule_code for r in load_vast_rules()}
        | {r.rule_code for r in load_csr_sla_rules()}
        | {r.rule_code for r in load_historical_pattern_rules()}
        | {r.rule_code for r in load_net_inf_rules()}
    )
    sop_codes = {r.rule_code for r in load_industry_sop_rules()}
    assert not (base_codes & sop_codes)
    assert not (other_codes & sop_codes)
