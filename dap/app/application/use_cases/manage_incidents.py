"""Incident REST resource use cases (POST/GET/list/bulk /api/v1/incidents,
docs/rule-management.md). Distinct from the pre-existing
EvaluateIncidentUseCase (unchanged, still what POST /api/v1/incidents/evaluate
calls): these persist an Incident record first, then reuse the exact same
EvaluateIncidentUseCase to run it through the pipeline -- "the Decision
Engine must evaluate incidents submitted through the API" is satisfied by
calling the identical, already-tested evaluation code path, not a parallel
implementation of it."""

from datetime import datetime, timezone
from typing import List, Optional

from app.domain.entities.incident import Incident
from app.domain.entities.decision import Decision
from app.domain.interfaces.incident_repository import IncidentRepository
from app.application.use_cases.evaluate_incident import EvaluateIncidentUseCase


class CreateIncidentUseCase:
    def __init__(self, incident_repository: IncidentRepository, evaluate_incident_use_case: EvaluateIncidentUseCase):
        self.incident_repository = incident_repository
        self.evaluate_incident_use_case = evaluate_incident_use_case

    def execute(
        self, incident_id: str, payload: dict, region: Optional[str] = None,
        tenant_id: Optional[str] = None, enriched_context: Optional[dict] = None,
        evaluate: bool = True,
    ) -> tuple[Incident, Optional[Decision]]:
        incident = Incident(
            incident_id=incident_id, payload=payload, enriched_context=enriched_context or {},
            region=region, tenant_id=tenant_id, status="received", created_at=datetime.now(timezone.utc),
        )
        self.incident_repository.save(incident)

        decision: Optional[Decision] = None
        if evaluate:
            try:
                decision = self.evaluate_incident_use_case.execute(incident, region=region, tenant=tenant_id)
                incident.status = "evaluated"
            except Exception:
                incident.status = "failed"
                self.incident_repository.save(incident)
                raise
            self.incident_repository.save(incident)
        return incident, decision


class GetIncidentUseCase:
    def __init__(self, incident_repository: IncidentRepository):
        self.incident_repository = incident_repository

    def execute(self, incident_id: str) -> Incident:
        incident = self.incident_repository.get(incident_id)
        if incident is None:
            raise ValueError(f"No such incident: {incident_id}")
        return incident


class ListIncidentsUseCase:
    def __init__(self, incident_repository: IncidentRepository):
        self.incident_repository = incident_repository

    def execute(self, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Incident]:
        return self.incident_repository.list_all(status=status, limit=limit, offset=offset)


class BulkCreateIncidentsUseCase:
    def __init__(self, create_incident_use_case: CreateIncidentUseCase):
        self.create_incident_use_case = create_incident_use_case

    def execute(self, incidents: List[dict], evaluate: bool = True) -> List[tuple[Incident, Optional[Decision]]]:
        results = []
        for item in incidents:
            incident_id = item["incidentId"]
            payload = {k: v for k, v in item.items() if k not in ("incidentId", "region", "tenantId", "context", "evaluate")}
            results.append(self.create_incident_use_case.execute(
                incident_id=incident_id, payload=payload, region=item.get("region"),
                tenant_id=item.get("tenantId"), enriched_context=item.get("context"), evaluate=evaluate,
            ))
        return results
