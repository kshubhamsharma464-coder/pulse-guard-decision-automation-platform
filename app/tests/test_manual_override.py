import pytest
from app.domain.entities.decision import Decision
from app.application.use_cases.override_decision import OverrideDecisionUseCase
from app.infrastructure.repositories.in_memory_manual_override_repository import InMemoryManualOverrideRepository


def _decision():
    return Decision(
        incident_id="INC-OVR", priority="High", risk_score=40, risk_band="MEDIUM",
        actions={"priority": "High", "dispatchEngineer": True}, mitigations={}, execution_plan=[],
        matched_rules=[], rejected_rules=[], suppressed_rules=[], compliance_constraints=[],
        confidence_score=100.0, degraded_context=False, explanation="test",
    )


def test_override_preserves_original_decision_and_records_reason():
    repo = InMemoryManualOverrideRepository()
    use_case = OverrideDecisionUseCase(repo)
    decision = _decision()

    override = use_case.execute(
        decision, operator="ankii",
        override_actions={"priority": "Critical", "dispatchEngineer": True},
        reason="On-site engineer reports downstream fiber cut not yet reflected in monitoring",
    )

    assert override.original_decision == {"priority": "High", "dispatchEngineer": True}
    assert override.override_decision["priority"] == "Critical"
    assert repo.list_by_decision("INC-OVR") == [override]
    # the automated decision itself is never mutated
    assert decision.actions["priority"] == "High"


def test_override_requires_a_reason():
    use_case = OverrideDecisionUseCase()
    with pytest.raises(ValueError, match="non-empty reason"):
        use_case.execute(_decision(), operator="ankii", override_actions={}, reason="   ")


def test_override_requires_an_operator():
    use_case = OverrideDecisionUseCase()
    with pytest.raises(ValueError, match="identified operator"):
        use_case.execute(_decision(), operator="", override_actions={}, reason="valid reason")
