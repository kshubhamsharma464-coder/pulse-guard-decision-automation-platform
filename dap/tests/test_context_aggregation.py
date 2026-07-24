from app.domain.entities.incident import Incident
from app.domain.interfaces.context_provider import ContextProvider
from app.domain.services.context_aggregation_service import ContextAggregationService


class _FailingProvider(ContextProvider):
    source_name = "flaky_source"

    def fetch(self, incident):
        raise TimeoutError("simulated source outage")


class _WorkingProvider(ContextProvider):
    source_name = "working_source"

    def fetch(self, incident):
        return {"engineerCapacityAvailable": False}


def test_aggregation_merges_working_sources_and_flags_failed_ones():
    service = ContextAggregationService(providers=[_WorkingProvider(), _FailingProvider()])
    incident = Incident(incident_id="INC-CTX", payload={})
    aggregated = service.aggregate(incident)

    assert aggregated.merged == {"engineerCapacityAvailable": False}
    assert aggregated.degraded_sources == ["flaky_source"]
    assert aggregated.is_degraded is True
    assert aggregated.total_sources == 2


def test_aggregation_wired_into_use_case_lowers_confidence_when_a_source_fails(rule_repo):
    from app.application.use_cases.evaluate_incident import EvaluateIncidentUseCase

    service = ContextAggregationService(providers=[_WorkingProvider(), _FailingProvider()])
    use_case = EvaluateIncidentUseCase(rule_repo, context_aggregation_service=service)

    incident = Incident(incident_id="INC-CTX-2", payload={"affectedUsers": 500})
    decision = use_case.execute(incident)

    assert decision.degraded_context is True
    assert decision.confidence_score == 50.0  # 1 of 2 sources live


def test_explicit_context_overrides_aggregated_defaults(rule_repo):
    from app.application.use_cases.evaluate_incident import EvaluateIncidentUseCase

    service = ContextAggregationService(providers=[_WorkingProvider()])  # sets engineerCapacityAvailable=False
    use_case = EvaluateIncidentUseCase(rule_repo, context_aggregation_service=service)

    incident = Incident(
        incident_id="INC-CTX-3",
        payload={"affectedUsers": 500},
        enriched_context={"engineerCapacityAvailable": True},  # caller override wins
    )
    decision = use_case.execute(incident)
    assert not any(r.rule_code == "R023" for r in decision.matched_rules)
