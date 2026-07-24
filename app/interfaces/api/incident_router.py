import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.domain.entities.incident import Incident
from app.interfaces.api.schemas import (
    IncidentEvaluateRequest, DecisionResponse, IncidentCreateRequest, IncidentBulkCreateRequest, IncidentResponse,
)
from app.interfaces.api.serializers import decision_to_dict, incident_to_dict
from app.interfaces.api.dependencies import (
    evaluate_incident_use_case, create_incident_use_case, get_incident_use_case,
    list_incidents_use_case, bulk_create_incidents_use_case, explain_decision_ai_use_case,
)
from app.interfaces.api.security import Principal, require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/incidents", tags=["Incidents"])


@router.post(
    "/evaluate",
    response_model=DecisionResponse,
    summary="Evaluate an incoming network incident",
    description=(
        "Runs the full Incident -> Context -> Risk Assessment -> Decision "
        "Orchestration -> Mitigation Plan -> Explainability pipeline against "
        "the active rule pack (currently the fixture-backed 35-rule seed set) "
        "and returns a fully explainable, auditable decision. The Context "
        "Aggregation Layer's 8 stub providers supply default (inert) context "
        "automatically; pass `context` in the request body to override "
        "specific fields for testing a scenario.\n\n"
        "Requires the 'incidents:evaluate' permission once auth is enabled "
        "(Settings.auth_required=true) -- open to anonymous callers otherwise.\n\n"
        "Pass `?explainWithAi=true` to additionally populate `aiExplanation` "
        "with a plain-language narrative of the decision from the configured "
        "AI provider (see AI_PROVIDER in .env). Purely additive -- `explanation` "
        "remains the real, deterministic explanation and is never altered. If "
        "the AI call fails or the provider is unreachable, `aiExplanation` is "
        "simply left null; the request never fails because of it."
    ),
)
def evaluate_incident(
    body: IncidentEvaluateRequest,
    explain_with_ai: bool = Query(
        False, alias="explainWithAi",
        description="If true, also asks the configured AI provider to narrate this "
        "decision in plain language (aiExplanation field). Never fails the request "
        "if the AI call fails -- the field is simply omitted (null).",
    ),
    _principal=Depends(require_permission("incidents:evaluate")),
):
    payload = body.model_dump(exclude={"context", "degradedContext"}, exclude_none=True)
    incident_id = payload.pop("incidentId")

    incident = Incident(
        incident_id=incident_id,
        payload=payload,
        enriched_context=body.context or {},
        degraded_context=bool(body.degradedContext),
    )
    decision = evaluate_incident_use_case.execute(incident)

    ai_explanation = None
    if explain_with_ai:
        try:
            ai_explanation = explain_decision_ai_use_case.execute(decision)
        except Exception:
            logger.warning(
                "AI explanation failed for incident %s -- returning decision without it",
                incident_id, exc_info=True,
            )

    return decision_to_dict(decision, ai_explanation=ai_explanation)


def _actor(principal: Principal) -> str:
    return principal.subject if principal.is_authenticated else "anonymous"


@router.post(
    "", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED,
    summary="Create an incident",
    description=(
        "Persists the incident and, unless `evaluate: false` is passed, immediately "
        "runs it through the same Decision Engine pipeline as POST /evaluate -- "
        "the response includes both the incident record and the resulting decision."
    ),
)
def create_incident(body: IncidentCreateRequest, principal: Principal = Depends(require_permission("incidents:create"))):
    payload = body.model_dump(exclude={"incidentId", "region", "tenantId", "context", "evaluate"}, exclude_none=True)
    try:
        incident, decision = create_incident_use_case.execute(
            incident_id=body.incidentId, payload=payload, region=body.region,
            tenant_id=body.tenantId, enriched_context=body.context, evaluate=body.evaluate,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return incident_to_dict(incident, decision)


@router.post(
    "/bulk", response_model=List[IncidentResponse], status_code=status.HTTP_201_CREATED,
    summary="Bulk create incidents",
    description=(
        "Pass `?explainWithAi=true` to additionally populate each resulting "
        "decision's `aiExplanation` field via the configured AI provider. "
        "Purely additive and best-effort -- if the AI call fails for a given "
        "incident (or the provider is unreachable), that incident's "
        "`aiExplanation` is simply left null; the batch never fails because of it."
    ),
)
def bulk_create_incidents(
    body: IncidentBulkCreateRequest,
    explain_with_ai: bool = Query(
        False, alias="explainWithAi",
        description="If true, also asks the configured AI provider to narrate each "
        "resulting decision in plain language (aiExplanation field per incident). "
        "Never fails the batch if an AI call fails -- the field is simply omitted (null).",
    ),
    principal: Principal = Depends(require_permission("incidents:create")),
):
    results = bulk_create_incidents_use_case.execute([i.model_dump() for i in body.incidents], evaluate=body.evaluate)

    dicts = []
    for incident, decision in results:
        ai_explanation = None
        if explain_with_ai and decision is not None:
            try:
                ai_explanation = explain_decision_ai_use_case.execute(decision)
            except Exception:
                logger.warning(
                    "AI explanation failed for incident %s -- returning decision without it",
                    incident.incident_id, exc_info=True,
                )
        dicts.append(incident_to_dict(incident, decision, ai_explanation=ai_explanation))
    return dicts


@router.get("/{incident_id}", response_model=IncidentResponse, summary="Get a persisted incident by ID")
def get_incident(incident_id: str, _principal: Principal = Depends(require_permission("incidents:read"))):
    try:
        incident = get_incident_use_case.execute(incident_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return incident_to_dict(incident)


@router.get("", response_model=List[IncidentResponse], summary="List persisted incidents")
def list_incidents(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    _principal: Principal = Depends(require_permission("incidents:read")),
):
    incidents = list_incidents_use_case.execute(status=status_filter, limit=limit, offset=offset)
    return [incident_to_dict(i) for i in incidents]
