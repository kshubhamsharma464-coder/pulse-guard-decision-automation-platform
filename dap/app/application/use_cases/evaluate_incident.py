from typing import Optional
from app.domain.entities.incident import Incident
from app.domain.entities.decision import Decision
from app.domain.interfaces.rule_repository import RuleRepository
from app.domain.interfaces.decision_repository import DecisionRepository
from app.domain.services.context_aggregation_service import ContextAggregationService
from app.application.orchestrator import PipelineOrchestrator


class EvaluateIncidentUseCase:
    """Real evaluation path. If a ContextAggregationService is supplied, it
    runs before the pipeline and any explicitly-supplied incident.enriched_context
    values win over the aggregated defaults (caller override). If a
    DecisionRepository is supplied, the resulting Decision is persisted --
    both are optional so existing unit tests that build a bare use case still
    work unchanged."""

    def __init__(
        self,
        rule_repository: RuleRepository,
        orchestrator: Optional[PipelineOrchestrator] = None,
        context_aggregation_service: Optional[ContextAggregationService] = None,
        decision_repository: Optional[DecisionRepository] = None,
    ):
        self.rule_repository = rule_repository
        self.orchestrator = orchestrator or PipelineOrchestrator()
        self.context_aggregation_service = context_aggregation_service
        self.decision_repository = decision_repository

    def execute(self, incident: Incident, region: Optional[str] = None, tenant: Optional[str] = None) -> Decision:
        if self.context_aggregation_service is not None:
            aggregated = self.context_aggregation_service.aggregate(incident)
            merged_context = dict(aggregated.merged)
            merged_context.update(incident.enriched_context)  # explicit context always wins
            incident.enriched_context = merged_context
            incident.context_sources_total = aggregated.total_sources
            incident.context_sources_degraded = len(aggregated.degraded_sources)
            incident.degraded_context = incident.degraded_context or aggregated.is_degraded

        rule_pack = self.rule_repository.get_active(region=region, tenant=tenant)
        decision = self.orchestrator.run(incident, rule_pack)

        if self.decision_repository is not None:
            self.decision_repository.save(decision)

        return decision
