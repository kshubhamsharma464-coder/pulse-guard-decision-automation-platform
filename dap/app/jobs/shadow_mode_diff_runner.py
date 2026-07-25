from typing import Any, Dict, List
from app.domain.entities.incident import Incident
from app.domain.entities.rule_pack import RulePack
from app.application.use_cases.promote_to_shadow import PromoteToShadowUseCase, ShadowDiffEntry


class ShadowModeDiffRunner:
    """Batch entry point for running the shadow-mode diff over a fixture/
    historical incident sample on a schedule, and summarizing results for
    human sign-off review before a candidate rule pack is activated."""

    def __init__(self):
        self.use_case = PromoteToShadowUseCase()

    def run(self, candidate_pack: RulePack, active_pack: RulePack, sample_incidents: List[Incident]) -> Dict[str, Any]:
        diffs: List[ShadowDiffEntry] = self.use_case.execute(candidate_pack, active_pack, sample_incidents)
        changed = [d for d in diffs if d.differs]
        return {
            "total_sampled": len(diffs),
            "changed_count": len(changed),
            "changed_incident_ids": [d.incident_id for d in changed],
            "diffs": diffs,
        }
