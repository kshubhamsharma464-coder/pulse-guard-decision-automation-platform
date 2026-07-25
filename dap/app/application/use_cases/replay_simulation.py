"""Phase 4 historical replay / impact analysis (POST /api/v1/simulate/replay):
take a real, already-persisted incident and re-run its exact original
payload against a different (or the current) rule pack, to answer "if this
incident came in today, would the decision be different?" -- without
mutating the original incident or its original decision (both are
append-only elsewhere in this codebase; replay reads them, never writes).

Distinct from WhatIfSimulationUseCase (simulate_rules.py), which takes an
arbitrary ad-hoc incident payload the caller supplies inline. Replay always
starts from a real IncidentRepository record, which is what makes it
"historical" rather than "hypothetical"."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.domain.entities.decision import Decision
from app.domain.interfaces.incident_repository import IncidentRepository
from app.domain.interfaces.decision_repository import DecisionRepository
from app.domain.interfaces.rule_repository import RuleRepository
from app.domain.interfaces.rule_pack_repository import RulePackRepository
from app.application.orchestrator import PipelineOrchestrator
from app.application.use_cases.rule_pack_resolution import resolve_rule_pack, rule_pack_ref_dict


def _diff(original: Optional[Decision], replayed: Decision) -> List[str]:
    """Human-readable list of what changed. Empty list (differs=False)
    when there's no prior decision to compare against -- a replay with no
    baseline still runs and returns a real decision, it just can't say
    whether it "changed" from anything."""
    if original is None:
        return []
    changes: List[str] = []
    if original.priority != replayed.priority:
        changes.append(f"priority: {original.priority!r} -> {replayed.priority!r}")
    if original.risk_band != replayed.risk_band:
        changes.append(f"riskBand: {original.risk_band!r} -> {replayed.risk_band!r}")
    if original.actions != replayed.actions:
        changes.append(f"decision actions changed: {original.actions!r} -> {replayed.actions!r}")
    original_codes = {r.rule_code for r in original.matched_rules}
    replayed_codes = {r.rule_code for r in replayed.matched_rules}
    if original_codes != replayed_codes:
        added = sorted(replayed_codes - original_codes)
        removed = sorted(original_codes - replayed_codes)
        if added:
            changes.append(f"newly matched rules: {added}")
        if removed:
            changes.append(f"no longer matched rules: {removed}")
    return changes


@dataclass
class ReplayResult:
    incident_id: str
    original_decision: Optional[Decision]
    replayed_decision: Decision
    rule_pack_used: Dict[str, Any]
    differs: bool
    differences: List[str] = field(default_factory=list)


class ReplaySimulationUseCase:
    def __init__(
        self,
        incident_repository: IncidentRepository,
        decision_repository: DecisionRepository,
        rule_repository: RuleRepository,
        rule_pack_repository: Optional[RulePackRepository] = None,
        orchestrator: Optional[PipelineOrchestrator] = None,
    ):
        self.incident_repository = incident_repository
        self.decision_repository = decision_repository
        self.rule_repository = rule_repository
        self.rule_pack_repository = rule_pack_repository
        self.orchestrator = orchestrator or PipelineOrchestrator()

    def execute(
        self, incident_id: str, *,
        pack_id: Optional[str] = None, name: Optional[str] = None, version: Optional[int] = None,
        region: Optional[str] = None, tenant: Optional[str] = None,
    ) -> ReplayResult:
        incident = self.incident_repository.get(incident_id)
        if incident is None:
            raise ValueError(f"No persisted incident found for replay: {incident_id}")

        pack, source = resolve_rule_pack(
            self.rule_repository, self.rule_pack_repository,
            pack_id=pack_id, name=name, version=version,
            region=region or incident.region, tenant=tenant or incident.tenant_id,
        )
        replayed_decision = self.orchestrator.run(incident, pack)
        original_decision = self.decision_repository.get(incident_id)
        differences = _diff(original_decision, replayed_decision)

        return ReplayResult(
            incident_id=incident_id,
            original_decision=original_decision,
            replayed_decision=replayed_decision,
            rule_pack_used=rule_pack_ref_dict(pack, source),
            differs=bool(differences),
            differences=differences,
        )
