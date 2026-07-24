import pytest
from app.domain.entities.rule import Rule
from app.domain.entities.rule_pack import RulePack
from app.domain.entities.incident import Incident
from app.domain.value_objects.rule_condition import RuleCondition
from app.application.use_cases.validate_rule_pack import ValidateRulePackUseCase
from app.application.use_cases.promote_to_shadow import PromoteToShadowUseCase
from app.application.use_cases.rollback_rule_pack import RollbackRulePackUseCase
from app.infrastructure.repositories.in_memory_rule_pack_repository import InMemoryRulePackRepository


def _simple_rule(code, threshold, priority_weight=50):
    return Rule(
        rule_code=code, name=f"Test rule {code}", description="", family="NETWORK_IMPACT",
        family_order=2, priority_weight=priority_weight, severity_band="High", contribution_score=10,
        conditions=RuleCondition({">": [{"var": "affectedUsers"}, threshold]}), exceptions=None,
        conflict_group=None, conflicts_with=[], is_suppressor=False, non_suppressible=False,
        cooldown_minutes=0, actions={"priority": "High", "dispatchEngineer": True},
    )


def test_validate_rejects_empty_pack():
    pack = RulePack(name="test-pack", version=1, status="draft", region=None, rules=[])
    result = ValidateRulePackUseCase().execute(pack)
    assert result.is_valid is False
    assert any("zero rules" in e for e in result.errors)


def test_validate_rejects_dangling_conflicts_with():
    rule = _simple_rule("T001", 1000)
    rule.conflicts_with = ["T999"]  # doesn't exist
    pack = RulePack(name="test-pack", version=1, status="draft", region=None, rules=[rule])
    result = ValidateRulePackUseCase().execute(pack)
    assert result.is_valid is False
    assert any("T999" in e for e in result.errors)


def test_validate_accepts_a_well_formed_pack():
    pack = RulePack(name="test-pack", version=1, status="draft", region=None, rules=[_simple_rule("T001", 1000)])
    result = ValidateRulePackUseCase().execute(pack)
    assert result.is_valid is True
    assert result.errors == []


def test_promote_to_shadow_reports_diff_between_active_and_candidate():
    active = RulePack(name="test-pack", version=1, status="active", region=None, rules=[_simple_rule("T001", 100000)])
    candidate = RulePack(name="test-pack", version=2, status="draft", region=None, rules=[_simple_rule("T001", 1000)], parent_version=1)

    incidents = [Incident(incident_id="INC-A", payload={"affectedUsers": 5000})]
    diffs = PromoteToShadowUseCase().execute(candidate, active, incidents)

    assert len(diffs) == 1
    assert diffs[0].differs is True  # active pack's threshold (100000) doesn't fire, candidate's (1000) does
    assert candidate.status == "shadow"


def test_promote_to_shadow_refuses_an_invalid_candidate():
    bad_rule = _simple_rule("T001", 1000)
    bad_rule.conflicts_with = ["MISSING"]
    candidate = RulePack(name="test-pack", version=2, status="draft", region=None, rules=[bad_rule])
    active = RulePack(name="test-pack", version=1, status="active", region=None, rules=[])

    with pytest.raises(ValueError, match="Cannot promote an invalid"):
        PromoteToShadowUseCase().execute(candidate, active, [])


def test_rollback_reactivates_parent_version():
    repo = InMemoryRulePackRepository()
    v1 = RulePack(name="test-pack", version=1, status="deprecated", region=None, rules=[_simple_rule("T001", 1000)])
    v2 = RulePack(name="test-pack", version=2, status="active", region=None, rules=[_simple_rule("T001", 2000)], parent_version=1)
    repo.save(v1)
    repo.save(v2)

    rolled_back = RollbackRulePackUseCase(repo).execute("test-pack", 2)

    assert rolled_back.version == 1
    assert rolled_back.status == "active"
    assert repo.get("test-pack", 2).status == "deprecated"


def test_rollback_fails_when_no_parent_version_recorded():
    repo = InMemoryRulePackRepository()
    v1 = RulePack(name="test-pack", version=1, status="active", region=None, rules=[])
    repo.save(v1)
    with pytest.raises(ValueError, match="no parent version"):
        RollbackRulePackUseCase(repo).execute("test-pack", 1)
