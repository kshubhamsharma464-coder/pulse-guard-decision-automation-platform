from dataclasses import dataclass
from typing import Any, Dict, List
from app.domain.entities.incident import Incident
from app.domain.entities.rule_pack import RulePack
from app.application.orchestrator import PipelineOrchestrator
from app.application.use_cases.validate_rule_pack import ValidateRulePackUseCase


@dataclass
class ShadowDiffEntry:
    incident_id: str
    active_decision: Dict[str, Any]
    candidate_decision: Dict[str, Any]
    differs: bool


class PromoteToShadowUseCase:
    """Design doc §8 step 4: run a validated draft against a sample of real or
    fixture incidents in parallel with the active pack, and return a diff --
    the human sign-off gate before activation. Rejects promotion outright if
    the candidate fails validate_rule_pack; shadow mode is not a substitute
    for structural validation, it comes after it."""

    def __init__(self, orchestrator: PipelineOrchestrator = None):
        self.orchestrator = orchestrator or PipelineOrchestrator()
        self.validator = ValidateRulePackUseCase()

    def execute(self, candidate_pack: RulePack, active_pack: RulePack, sample_incidents: List[Incident]) -> List[ShadowDiffEntry]:
        validation = self.validator.execute(candidate_pack)
        if not validation.is_valid:
            raise ValueError(f"Cannot promote an invalid rule pack to shadow: {validation.errors}")

        candidate_pack.status = "shadow"
        diffs: List[ShadowDiffEntry] = []
        for incident in sample_incidents:
            active_decision = self.orchestrator.run(incident, active_pack)
            candidate_decision = self.orchestrator.run(incident, candidate_pack)
            differs = (
                active_decision.priority != candidate_decision.priority
                or active_decision.actions != candidate_decision.actions
            )
            diffs.append(ShadowDiffEntry(
                incident_id=incident.incident_id,
                active_decision=active_decision.actions,
                candidate_decision=candidate_decision.actions,
                differs=differs,
            ))
        return diffs
