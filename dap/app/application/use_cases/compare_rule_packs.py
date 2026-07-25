"""Phase 4 rule-version comparison (POST /api/v1/simulate/compare): run a
batch of incidents through two rule packs -- a baseline (defaults to
whatever's currently active on the hot evaluation path) and a candidate
(any versioned pack, typically a not-yet-published Draft) -- and report
where the two disagree.

Deliberately a SEPARATE use case from PromoteToShadowUseCase
(promote_to_shadow.py), not a generalization of it in place: promotion is
a gated workflow step (it requires the candidate to pass
ValidateRulePackUseCase and it mutates the candidate's status to "shadow"
as a side effect -- see that file's own docstring) that existing tests
already depend on behaving exactly that way. Comparison here is a pure,
read-only analysis tool a rule editor can run at any time, against any two
pack references, with no validation gate and no status mutation -- adding
those semantics to PromoteToShadowUseCase would change what its existing
callers get. Both reuse the same PipelineOrchestrator.run() under the
hood, so neither one is "a different, less trustworthy code path" than
production."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.domain.entities.incident import Incident
from app.domain.entities.rule_pack import RulePack
from app.domain.interfaces.incident_repository import IncidentRepository
from app.domain.interfaces.rule_repository import RuleRepository
from app.domain.interfaces.rule_pack_repository import RulePackRepository
from app.application.orchestrator import PipelineOrchestrator
from app.application.use_cases.rule_pack_resolution import resolve_rule_pack, rule_pack_ref_dict


@dataclass
class RulePackDiffEntry:
    incident_id: str
    baseline_priority: Optional[str]
    candidate_priority: Optional[str]
    baseline_decision: Dict[str, Any]
    candidate_decision: Dict[str, Any]
    differs: bool


@dataclass
class CompareResult:
    baseline: Dict[str, Any]
    candidate: Dict[str, Any]
    total_incidents: int
    differing_count: int
    diffs: List[RulePackDiffEntry] = field(default_factory=list)


class CompareRulePacksUseCase:
    def __init__(
        self,
        incident_repository: IncidentRepository,
        rule_repository: RuleRepository,
        rule_pack_repository: Optional[RulePackRepository] = None,
        orchestrator: Optional[PipelineOrchestrator] = None,
        max_incidents: int = 200,
    ):
        self.incident_repository = incident_repository
        self.rule_repository = rule_repository
        self.rule_pack_repository = rule_pack_repository
        self.orchestrator = orchestrator or PipelineOrchestrator()
        self.max_incidents = max_incidents

    def _resolve_incidents(self, incident_ids: List[str], inline_incidents: List[Incident]) -> List[Incident]:
        resolved: List[Incident] = []
        for incident_id in incident_ids:
            incident = self.incident_repository.get(incident_id)
            if incident is None:
                raise ValueError(f"No persisted incident found for comparison: {incident_id}")
            resolved.append(incident)
        resolved.extend(inline_incidents)
        if not resolved:
            raise ValueError("At least one incident (via incidentIds or inline incidents) is required to compare rule packs")
        if len(resolved) > self.max_incidents:
            raise ValueError(
                f"Comparison accepts at most {self.max_incidents} incidents per request (got {len(resolved)})"
            )
        return resolved

    def execute(
        self,
        *,
        incident_ids: Optional[List[str]] = None,
        inline_incidents: Optional[List[Incident]] = None,
        baseline_pack_id: Optional[str] = None, baseline_name: Optional[str] = None, baseline_version: Optional[int] = None,
        candidate_pack_id: Optional[str] = None, candidate_name: Optional[str] = None, candidate_version: Optional[int] = None,
        region: Optional[str] = None, tenant: Optional[str] = None,
    ) -> CompareResult:
        incidents = self._resolve_incidents(incident_ids or [], inline_incidents or [])

        baseline_pack, baseline_source = resolve_rule_pack(
            self.rule_repository, self.rule_pack_repository,
            pack_id=baseline_pack_id, name=baseline_name, version=baseline_version,
            region=region, tenant=tenant,
        )
        if not (candidate_pack_id or candidate_name):
            raise ValueError(
                "A candidate rule pack must be specified (candidateRulePackId, or "
                "candidateRulePackName[+candidateRulePackVersion]) -- comparison needs two packs to compare"
            )
        candidate_pack, candidate_source = resolve_rule_pack(
            self.rule_repository, self.rule_pack_repository,
            pack_id=candidate_pack_id, name=candidate_name, version=candidate_version,
            region=region, tenant=tenant,
        )

        diffs: List[RulePackDiffEntry] = []
        for incident in incidents:
            baseline_decision = self.orchestrator.run(incident, baseline_pack)
            candidate_decision = self.orchestrator.run(incident, candidate_pack)
            differs = (
                baseline_decision.priority != candidate_decision.priority
                or baseline_decision.actions != candidate_decision.actions
            )
            diffs.append(RulePackDiffEntry(
                incident_id=incident.incident_id,
                baseline_priority=baseline_decision.priority,
                candidate_priority=candidate_decision.priority,
                baseline_decision=baseline_decision.actions,
                candidate_decision=candidate_decision.actions,
                differs=differs,
            ))

        return CompareResult(
            baseline=rule_pack_ref_dict(baseline_pack, baseline_source),
            candidate=rule_pack_ref_dict(candidate_pack, candidate_source),
            total_incidents=len(incidents),
            differing_count=sum(1 for d in diffs if d.differs),
            diffs=diffs,
        )
