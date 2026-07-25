"""Backward-compatibility locks: proves the additions of the SLA, vast, and
CSR-SLA rule packs (all wired only into the API composition root's
CompositeRuleRepository) leave every pre-existing direct usage of
InMemoryRuleRepository byte-for-byte unaffected, and that the fully merged
4-pack repository still produces the exact original INC-101 result."""

from app.infrastructure.repositories.in_memory_rule_repository import InMemoryRuleRepository
from app.infrastructure.repositories.composite_rule_repository import CompositeRuleRepository
from app.infrastructure.repositories.sla_rule_pack_loader import load_sla_rules
from app.infrastructure.repositories.vast_rule_pack_loader import load_vast_rules
from app.infrastructure.repositories.csr_sla_rule_pack_loader import load_csr_sla_rules
from app.infrastructure.repositories.historical_pattern_rule_pack_loader import load_historical_pattern_rules
from app.infrastructure.repositories.net_inf_rule_pack_loader import load_net_inf_rules
from app.application.use_cases.evaluate_incident import EvaluateIncidentUseCase
from app.application.orchestrator import PipelineOrchestrator
from app.domain.entities.incident import Incident


def test_bare_in_memory_rule_repository_still_exactly_thirty_five_rules():
    """The exact construction used throughout tests/conftest.py -- must stay
    untouched by every rule-pack addition."""
    pack = InMemoryRuleRepository().get_active()
    assert len(pack.rules) == 35


def test_inc_101_matches_identical_rules_through_fully_merged_six_pack_repository():
    base_pack = InMemoryRuleRepository().get_active()
    merged = CompositeRuleRepository(
        name=base_pack.name, version=base_pack.version + 1, region=base_pack.region,
        rule_groups=[base_pack.rules, load_sla_rules(), load_vast_rules(), load_csr_sla_rules(),
                     load_historical_pattern_rules(), load_net_inf_rules()],
    )
    assert len(merged.get_active().rules) == 35 + 12 + 30 + 18 + 30 + 14

    use_case = EvaluateIncidentUseCase(merged, orchestrator=PipelineOrchestrator())
    incident = Incident(incident_id="INC-101", payload={
        "incidentId": "INC-101", "towerId": "T-Delhi-101", "region": "Delhi",
        "affectedUsers": 15000, "vipCustomersAffected": True, "networkLoad": 94,
        "slaTier": "Gold", "maintenanceWindow": False, "weatherSeverity": "Moderate",
        "historicalFailures": 4, "incidentType": "Tower Down",
    })
    decision = use_case.execute(incident)
    matched_codes = {r.rule_code for r in decision.matched_rules}
    assert matched_codes == {"R001", "R004", "R007", "R009", "R012"}
    assert decision.priority == "Critical"


def test_csr_sla_conflict_resolution_picks_highest_weight_on_multi_match():
    base_pack = InMemoryRuleRepository().get_active()
    merged = CompositeRuleRepository(
        name=base_pack.name, version=base_pack.version + 1, region=base_pack.region,
        rule_groups=[base_pack.rules, load_csr_sla_rules()],
    )
    use_case = EvaluateIncidentUseCase(merged, orchestrator=PipelineOrchestrator())
    incident = Incident(incident_id="INC-CSR-1", payload={
        "slaBreached": True, "isClosed": False,
        "customerTier": "gold", "customerImpact": True, "severity": "critical", "isOpen": True,
    })
    decision = use_case.execute(incident)
    matched_codes = {r.rule_code for r in decision.matched_rules}
    assert {"CSR-SLA-001", "CSR-SLA-004"}.issubset(matched_codes)
    # CSR-SLA-004 (priority 950) must win the shared conflict_group over CSR-SLA-001 (900)
    assert decision.actions["escalationTarget"] == "noc_level_3"
    assert decision.actions["decision"] == "escalate"


def test_his_pack_conflict_resolution_picks_highest_weight_on_multi_match():
    base_pack = InMemoryRuleRepository().get_active()
    merged = CompositeRuleRepository(
        name=base_pack.name, version=base_pack.version + 1, region=base_pack.region,
        rule_groups=[base_pack.rules, load_historical_pattern_rules()],
    )
    use_case = EvaluateIncidentUseCase(merged, orchestrator=PipelineOrchestrator())
    # HIS022 (Low MTBSI, weight 975) and HIS023 (Rising complaints, weight 945)
    # both fire on this payload -- HIS022 must win the shared conflict_group.
    incident = Incident(incident_id="INC-HIS-MULTI", payload={
        "asset": {"mtbsiHours": 40},
        "serviceImpactMinutes": 15,
        "customer": {"complaints24h": 25, "complaintTrend7d": 0.3},
    })
    decision = use_case.execute(incident)
    matched_codes = {r.rule_code for r in decision.matched_rules}
    assert {"HIS022", "HIS023"}.issubset(matched_codes)
    assert decision.actions["hisAssignmentGroup"] == "Engineering L3"
    assert decision.actions["hisDecision"] == "ESCALATE_ENGINEERING"


def test_his_pack_decision_field_does_not_collide_with_csr_sla_pack_decision_field():
    """Both packs can independently match the same incident without either
    overwriting the other's differently-named output -- proof the his*
    namespace choice actually prevents the cross-pack interference the
    loader's docstring warns about."""
    base_pack = InMemoryRuleRepository().get_active()
    merged = CompositeRuleRepository(
        name=base_pack.name, version=base_pack.version + 1, region=base_pack.region,
        rule_groups=[base_pack.rules, load_csr_sla_rules(), load_historical_pattern_rules()],
    )
    use_case = EvaluateIncidentUseCase(merged, orchestrator=PipelineOrchestrator())
    incident = Incident(incident_id="INC-CROSS", payload={
        # CSR-SLA-004 (SLA breach)
        "slaBreached": True, "isClosed": False,
        # HIS015 (fiber cut hotspot)
        "asset": {"locationHotspotFiberCuts": True},
        "symptomType": "transmission_down",
    })
    decision = use_case.execute(incident)
    matched_codes = {r.rule_code for r in decision.matched_rules}
    assert {"CSR-SLA-004", "HIS015"}.issubset(matched_codes)
    assert decision.actions["decision"] == "escalate"           # CSR-SLA's own field, untouched
    assert decision.actions["hisDecision"] == "DISPATCH_FIELD_EMERGENCY"  # HIS's own field, untouched


def test_net_inf_and_csr_sla_disagreement_stays_independently_visible():
    """NET-INF-010 and CSR-SLA-013 fire on the exact same condition
    (unapproved maintenance with customer impact) but disagree on
    escalationTarget. Because NET-INF's fields are namespaced, both
    opinions survive in the decision output instead of one silently
    overwriting the other."""
    base_pack = InMemoryRuleRepository().get_active()
    merged = CompositeRuleRepository(
        name=base_pack.name, version=base_pack.version + 1, region=base_pack.region,
        rule_groups=[base_pack.rules, load_csr_sla_rules(), load_net_inf_rules()],
    )
    use_case = EvaluateIncidentUseCase(merged, orchestrator=PipelineOrchestrator())
    incident = Incident(incident_id="INC-DISAGREE", payload={
        "inMaintenanceWindow": True, "changeApproved": False, "customerImpact": True,
    })
    decision = use_case.execute(incident)
    matched_codes = {r.rule_code for r in decision.matched_rules}
    assert {"CSR-SLA-013", "NET-INF-010"}.issubset(matched_codes)
    assert decision.actions["escalationTarget"] == "noc_level_3"
    assert decision.actions["netInfEscalationTarget"] == "engineering_oncall"
