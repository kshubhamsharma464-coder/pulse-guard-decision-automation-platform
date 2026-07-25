from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from app.interfaces.api.dependencies import decision_repository, decision_distribution_use_case
from app.interfaces.api.schemas import DecisionResponse, DecisionsDistributionResponse
from app.interfaces.api.serializers import decision_to_dict, distribution_result_to_dict
from app.interfaces.api.security import require_permission

router = APIRouter(prefix="/api/v1/decisions", tags=["Decisions"])

# incident_router (POST /incidents/evaluate) is the submission path -- it
# creates a decision. This router is the retrieval/audit path -- it only
# ever reads what evaluate_incident_use_case already persisted, it never
# triggers a new evaluation.


@router.get(
    "/distribution",
    response_model=DecisionsDistributionResponse,
    summary="Aggregate decision distribution (Phase 4)",
    description=(
        "Priority/risk-band counts, average risk and confidence scores, "
        "and degraded-context rate across the most recent `limit` "
        "persisted decisions (default 10,000, newest first). Registered "
        "before GET /{incident_id} so 'distribution' is never mistaken "
        "for an incident id. Requires 'decisions:read'."
    ),
)
def get_decision_distribution(
    limit: int = Query(10_000, ge=1, le=50_000),
    _principal=Depends(require_permission("decisions:read")),
):
    result = decision_distribution_use_case.execute(limit=limit)
    return distribution_result_to_dict(result)


@router.get(
    "/{incident_id}",
    response_model=DecisionResponse,
    summary="Get the latest decision for an incident",
    description="Returns the most recent decision on record for this incident_id. 404 if none exists yet.",
)
def get_decision(incident_id: str, _principal=Depends(require_permission("decisions:read"))):
    decision = decision_repository.get(incident_id)
    if decision is None:
        raise HTTPException(status_code=404, detail=f"No decision found for incident '{incident_id}'")
    return decision_to_dict(decision)


@router.get(
    "/{incident_id}/history",
    response_model=List[DecisionResponse],
    summary="Get every decision ever produced for an incident",
    description=(
        "Decisions are immutable and append-only (design doc §7/§9) -- a "
        "context change after incident creation produces a new, linked "
        "decision rather than mutating the original. This returns the full "
        "sequence in the order they were made."
    ),
)
def get_decision_history(incident_id: str, _principal=Depends(require_permission("decisions:read"))):
    history = decision_repository.list_by_incident(incident_id)
    if not history:
        raise HTTPException(status_code=404, detail=f"No decisions found for incident '{incident_id}'")
    return [decision_to_dict(d) for d in history]
