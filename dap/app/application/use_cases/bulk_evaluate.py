"""Phase 4 bulk evaluation (POST /api/v1/evaluate/bulk): evaluate many
incident payloads in one request and return aggregate success/failure
counts, decision distribution, and execution metrics -- built for
load-testing, backfills, and bulk imports, distinct from the one-at-a-time
POST /api/v1/incidents/evaluate.

Reuses EvaluateIncidentUseCase per item rather than re-implementing
evaluation -- this is the SAME production code path (context aggregation,
orchestrator, optional persistence), just called in a loop with per-item
error isolation so one malformed incident in a batch of thousands doesn't
abort the other 1,999. `persist` selects between two pre-wired
EvaluateIncidentUseCase instances (see dependencies.py) that differ only in
whether a DecisionRepository is attached -- not a re-implementation of
persistence logic, just choosing which already-correct instance to call."""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.domain.entities.incident import Incident
from app.application.use_cases.evaluate_incident import EvaluateIncidentUseCase


@dataclass
class BulkEvaluateResultEntry:
    incident_id: Optional[str]
    success: bool
    priority: Optional[str] = None
    risk_band: Optional[str] = None
    error: Optional[str] = None


@dataclass
class BulkEvaluateResult:
    total: int
    succeeded: int
    failed: int
    execution_time_ms: float
    average_time_ms_per_incident: float
    priority_distribution: Dict[str, int]
    risk_band_distribution: Dict[str, int]
    results: List[BulkEvaluateResultEntry] = field(default_factory=list)


_PAYLOAD_EXCLUDED_KEYS = {"incidentId", "region", "tenantId", "context", "degradedContext"}


class BulkEvaluateUseCase:
    def __init__(
        self,
        persisting_use_case: EvaluateIncidentUseCase,
        dry_run_use_case: EvaluateIncidentUseCase,
        max_items: int = 2000,
    ):
        self.persisting_use_case = persisting_use_case
        self.dry_run_use_case = dry_run_use_case
        self.max_items = max_items

    def execute(
        self, incidents_data: List[Dict[str, Any]], *,
        persist: bool = True, region: Optional[str] = None, tenant: Optional[str] = None,
    ) -> BulkEvaluateResult:
        total = len(incidents_data)
        if total > self.max_items:
            raise ValueError(f"Bulk evaluate accepts at most {self.max_items} incidents per request (got {total})")

        use_case = self.persisting_use_case if persist else self.dry_run_use_case
        priority_distribution: Dict[str, int] = {}
        risk_band_distribution: Dict[str, int] = {}
        results: List[BulkEvaluateResultEntry] = []
        succeeded = 0
        failed = 0

        start = time.perf_counter()
        for item in incidents_data:
            incident_id = item.get("incidentId")
            item_region = item.get("region") or region
            item_tenant = item.get("tenantId") or tenant
            try:
                if not incident_id:
                    raise ValueError("incidentId is required for every item in a bulk evaluation")
                payload = {k: v for k, v in item.items() if k not in _PAYLOAD_EXCLUDED_KEYS}
                incident = Incident(
                    incident_id=incident_id,
                    payload=payload,
                    enriched_context=item.get("context") or {},
                    degraded_context=bool(item.get("degradedContext", False)),
                    region=item_region,
                    tenant_id=item_tenant,
                )
                decision = use_case.execute(incident, region=item_region, tenant=item_tenant)
                succeeded += 1
                priority_key = decision.priority or "Unknown"
                priority_distribution[priority_key] = priority_distribution.get(priority_key, 0) + 1
                risk_band_distribution[decision.risk_band] = risk_band_distribution.get(decision.risk_band, 0) + 1
                results.append(BulkEvaluateResultEntry(
                    incident_id=incident_id, success=True, priority=decision.priority, risk_band=decision.risk_band,
                ))
            except Exception as exc:
                failed += 1
                results.append(BulkEvaluateResultEntry(incident_id=incident_id, success=False, error=str(exc)))
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        return BulkEvaluateResult(
            total=total,
            succeeded=succeeded,
            failed=failed,
            execution_time_ms=elapsed_ms,
            average_time_ms_per_incident=(elapsed_ms / total) if total else 0.0,
            priority_distribution=priority_distribution,
            risk_band_distribution=risk_band_distribution,
            results=results,
        )
