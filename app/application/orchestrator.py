from app.domain.entities.incident import Incident
from app.domain.entities.rule_pack import RulePack
from app.domain.entities.decision import Decision
from app.domain.services.policy_engine import PolicyEngine
from app.domain.services.conflict_resolver import ConflictResolver
from app.domain.services.compliance_applier import ComplianceApplier
from app.domain.services.risk_scorer import RiskScorer
from app.domain.services.execution_plan_builder import ExecutionPlanBuilder
from app.domain.services.explainability_builder import ExplainabilityBuilder
from app.domain.services.confidence_calculator import ConfidenceCalculator
from app.domain.services.sla_matrix_lookup import SlaMatrixLookup
from typing import Optional


class PipelineOrchestrator:
    """Incident -> Context -> Risk Assessment -> Decision Orchestration -> Mitigation
    Plan -> Explainability -> Audit Trail (design doc positioning statement).

    Shared by evaluate_incident and simulate_rules use cases -- persistence is the
    only thing that differs between them, per architecture-review.md §1."""

    def __init__(self, sla_matrix_lookup: Optional[SlaMatrixLookup] = None):
        self.policy_engine = PolicyEngine()
        self.conflict_resolver = ConflictResolver()
        self.compliance_applier = ComplianceApplier()
        self.risk_scorer = RiskScorer()
        self.execution_plan_builder = ExecutionPlanBuilder()
        self.explainability_builder = ExplainabilityBuilder()
        self.confidence_calculator = ConfidenceCalculator()
        # Optional and None by default -- every existing PipelineOrchestrator()
        # call site (tests, promote_to_shadow, etc.) is unaffected. Only the
        # composition root wires a real SlaMatrixLookup in.
        self.sla_matrix_lookup = sla_matrix_lookup

    def run(self, incident: Incident, rule_pack: RulePack) -> Decision:
        matched, rejected = self.policy_engine.evaluate(rule_pack, incident)

        actions, mitigations, suppressed = self.conflict_resolver.resolve(matched)
        actions, compliance_constraints = self.compliance_applier.apply(rule_pack, incident, actions)

        if self.sla_matrix_lookup is not None and "targetSLA" not in actions:
            matrix_entry = self.sla_matrix_lookup.resolve(incident.payload.get("customerTier"), actions.get("priority"))
            if matrix_entry:
                actions["targetSLA"] = f"{matrix_entry['responseMinutes']} minutes"
                actions["slaResolutionMinutes"] = matrix_entry["resolutionMinutes"]

        suppressed_codes = {s["rule_code"] for s in suppressed}
        risk_score, risk_band = self.risk_scorer.score(matched, suppressed_codes)

        execution_plan = self.execution_plan_builder.build(actions, matched)
        explanation = self.explainability_builder.build(matched, rejected, suppressed, risk_score, risk_band, actions)
        matched_trace = self.explainability_builder.matched_trace(matched)

        total_sources = incident.context_sources_total or (len(incident.enriched_context) or 1)
        degraded_sources = incident.context_sources_degraded or (1 if incident.degraded_context else 0)
        confidence = self.confidence_calculator.compute(
            total_context_sources=total_sources,
            degraded_sources=degraded_sources,
        )

        return Decision(
            incident_id=incident.incident_id,
            priority=actions.get("priority"),
            risk_score=risk_score,
            risk_band=risk_band,
            actions=actions,
            mitigations=mitigations,
            execution_plan=execution_plan,
            matched_rules=matched_trace,
            rejected_rules=rejected,
            suppressed_rules=suppressed,
            compliance_constraints=compliance_constraints,
            confidence_score=confidence,
            degraded_context=incident.degraded_context,
            explanation=explanation,
        )
