from typing import Any, Dict
from app.domain.entities.decision import Decision
from app.domain.interfaces.ai_provider import AIProvider


class ExplainDecisionAIUseCase:
    """AI-assisted, plain-language narrative of an ALREADY-COMPUTED
    Decision -- strictly additive to Decision.explanation (the
    deterministic explanation ExplainabilityBuilder always produces,
    with zero AI involvement, available even when AI_PROVIDER=stub or an
    LLM call fails). This use case runs AFTER the decision exists and
    cannot alter it -- it only ever reads a plain-fact snapshot of it and
    passes those facts to the AI provider for narration. See
    app/domain/interfaces/ai_provider.py's docstring for the full safety
    boundary.

    Builds its own fact dict (_decision_facts below) rather than importing
    app/interfaces/api/serializers.decision_to_dict -- application/ must
    not depend on interfaces/ (Clean Architecture's dependency rule runs
    inward only); the two happen to produce a similar shape by
    coincidence of both describing the same entity, not because one calls
    the other."""

    def __init__(self, ai_provider: AIProvider):
        self.ai_provider = ai_provider

    def execute(self, decision: Decision) -> str:
        return self.ai_provider.explain_decision(_decision_facts(decision))


def _decision_facts(decision: Decision) -> Dict[str, Any]:
    return {
        "incidentId": decision.incident_id,
        "priority": decision.priority,
        "riskScore": decision.risk_score,
        "riskBand": decision.risk_band,
        "decision": decision.actions,
        "matchedRules": [m.__dict__ for m in decision.matched_rules],
        "confidenceScore": decision.confidence_score,
        "degradedContext": decision.degraded_context,
    }
