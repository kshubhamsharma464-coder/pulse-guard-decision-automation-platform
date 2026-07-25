from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.domain.entities.incident import Incident
from app.domain.entities.rule_pack import RulePack
from app.domain.entities.decision import Decision
from app.domain.interfaces.rule_repository import RuleRepository
from app.domain.interfaces.rule_pack_repository import RulePackRepository
from app.application.orchestrator import PipelineOrchestrator
from app.application.use_cases.rule_pack_resolution import resolve_rule_pack, rule_pack_ref_dict


class SimulateRulesUseCase:
    """Dry-run path used by the shadow-mode validation flow (design doc §8): evaluate
    a draft/candidate RulePack against a real or fixture incident without persisting
    anything. Reuses the same orchestrator as the real evaluation path on purpose --
    a simulation that runs different code than production isn't a trustworthy simulation."""

    def __init__(self, orchestrator: Optional[PipelineOrchestrator] = None):
        self.orchestrator = orchestrator or PipelineOrchestrator()

    def execute(self, incident: Incident, candidate_rule_pack: RulePack) -> Decision:
        return self.orchestrator.run(incident, candidate_rule_pack)


@dataclass
class WhatIfResult:
    decision: Decision
    rule_pack_used: Dict[str, Any]


class WhatIfSimulationUseCase:
    """Phase 4 what-if analysis (POST /api/v1/simulate): run an ad-hoc or
    real incident payload against either the currently-active rule pack
    (the default -- "what would production do with this payload right
    now") or an explicit rule-pack reference, including a still-Draft
    version that was never activated ("what would this candidate rule
    change do, before I publish it").

    Deliberately thin: SimulateRulesUseCase already does the one thing
    that must never diverge from production (running the real
    PipelineOrchestrator) -- this use case's only job is resolving which
    RulePack to hand it, via the shared resolve_rule_pack() helper, and
    never persists anything (no DecisionRepository is even accepted)."""

    def __init__(
        self,
        rule_repository: RuleRepository,
        rule_pack_repository: Optional[RulePackRepository] = None,
        orchestrator: Optional[PipelineOrchestrator] = None,
    ):
        self.rule_repository = rule_repository
        self.rule_pack_repository = rule_pack_repository
        self.simulator = SimulateRulesUseCase(orchestrator)

    def execute(
        self, incident: Incident, *,
        pack_id: Optional[str] = None, name: Optional[str] = None, version: Optional[int] = None,
        region: Optional[str] = None, tenant: Optional[str] = None,
    ) -> WhatIfResult:
        pack, source = resolve_rule_pack(
            self.rule_repository, self.rule_pack_repository,
            pack_id=pack_id, name=name, version=version, region=region, tenant=tenant,
        )
        decision = self.simulator.execute(incident, pack)
        return WhatIfResult(decision=decision, rule_pack_used=rule_pack_ref_dict(pack, source))
