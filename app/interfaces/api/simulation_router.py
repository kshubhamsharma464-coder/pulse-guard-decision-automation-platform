"""Phase 4: simulation engine + bulk evaluation. Three read-only analysis
endpoints under /api/v1/simulate (what-if, historical replay, rule-version
comparison -- none of them ever persist a decision) plus one write-capable
one, POST /api/v1/evaluate/bulk, which behaves exactly like
POST /api/v1/incidents/evaluate run many times over (same persistence
semantics, opt-out via `persist: false`).

Every use case here is deliberately built on top of the exact same
PipelineOrchestrator/EvaluateIncidentUseCase the real evaluation path uses
(see simulate_rules.py, replay_simulation.py, compare_rule_packs.py,
bulk_evaluate.py's module docstrings) -- a simulation subsystem that
doesn't share code with production isn't trustworthy, it's a second,
divergent decision engine wearing a simulation's name."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.domain.entities.incident import Incident
from app.interfaces.api.schemas import (
    SimulateRequest, SimulateResponse,
    ReplaySimulationRequest, ReplaySimulationResponse,
    CompareRulePacksRequest, CompareRulePacksResponse,
    BulkEvaluateRequest, BulkEvaluateResponse,
)
from app.interfaces.api.serializers import (
    what_if_result_to_dict, replay_result_to_dict, compare_result_to_dict,
    bulk_evaluate_result_to_dict,
)
from app.interfaces.api.dependencies import (
    what_if_simulation_use_case, replay_simulation_use_case, compare_rule_packs_use_case,
    bulk_evaluate_use_case,
)
from app.interfaces.api.security import require_permission

simulation_router = APIRouter(prefix="/api/v1/simulate", tags=["Simulation"])
bulk_evaluate_router = APIRouter(prefix="/api/v1/evaluate", tags=["Decisions"])


def _incident_from_request(body) -> Incident:
    payload = body.model_dump(exclude={"context", "degradedContext"}, exclude_none=True)
    incident_id = payload.pop("incidentId")
    return Incident(
        incident_id=incident_id, payload=payload,
        enriched_context=body.context or {}, degraded_context=bool(body.degradedContext),
    )


@simulation_router.post(
    "",
    response_model=SimulateResponse,
    summary="What-if simulation -- evaluate an incident without persisting anything",
    description=(
        "Runs the same pipeline as POST /api/v1/incidents/evaluate against "
        "either the currently-active rule pack (default) or an explicit "
        "rulePackId/rulePackName -- including a still-Draft version that "
        "was never activated. Nothing is written: no incident, no "
        "decision, no audit entry. Requires 'simulation:run'."
    ),
)
def simulate(body: SimulateRequest, _principal=Depends(require_permission("simulation:run"))):
    incident = _incident_from_request(body.incident)
    try:
        result = what_if_simulation_use_case.execute(
            incident, pack_id=body.rulePackId, name=body.rulePackName, version=body.rulePackVersion,
            region=body.region, tenant=body.tenantId,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return what_if_result_to_dict(result)


@simulation_router.post(
    "/replay",
    response_model=ReplaySimulationResponse,
    summary="Historical replay -- re-run a persisted incident's original payload against a (possibly different) rule pack",
    description=(
        "Fetches a previously-persisted incident by id and re-runs it "
        "through the pipeline against the requested rule pack (defaults to "
        "whatever's currently active). Compares the result against the "
        "most recent decision on record for that incident, if any, and "
        "reports whether -- and how -- the outcome would differ. Read-only: "
        "the original incident and decision are never modified. Requires "
        "'simulation:run'."
    ),
)
def replay(body: ReplaySimulationRequest, _principal=Depends(require_permission("simulation:run"))):
    try:
        result = replay_simulation_use_case.execute(
            body.incidentId, pack_id=body.rulePackId, name=body.rulePackName, version=body.rulePackVersion,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return replay_result_to_dict(result)


@simulation_router.post(
    "/compare",
    response_model=CompareRulePacksResponse,
    summary="Rule-version comparison -- run a batch of incidents through two rule packs and diff the results",
    description=(
        "Runs every incident in `incidentIds` (persisted, fetched by id) "
        "and `incidents` (inline payloads) through both a baseline rule "
        "pack (defaults to the currently-active one) and a required "
        "candidate rule pack, and reports where their decisions disagree. "
        "Purely read-only impact analysis -- no validation gate, no status "
        "change on the candidate pack (contrast with the Draft->Published "
        "shadow-promotion workflow in docs/rule-management.md, which does "
        "gate and does mutate status). Capped at "
        "Settings.simulation_max_compare_incidents incidents per request. "
        "Requires 'simulation:run'."
    ),
)
def compare(body: CompareRulePacksRequest, _principal=Depends(require_permission("simulation:run"))):
    inline_incidents = [_incident_from_request(i) for i in body.incidents]
    try:
        result = compare_rule_packs_use_case.execute(
            incident_ids=body.incidentIds, inline_incidents=inline_incidents,
            baseline_pack_id=body.baselineRulePackId, baseline_name=body.baselineRulePackName, baseline_version=body.baselineRulePackVersion,
            candidate_pack_id=body.candidateRulePackId, candidate_name=body.candidateRulePackName, candidate_version=body.candidateRulePackVersion,
            region=body.region, tenant=body.tenantId,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return compare_result_to_dict(result)


@bulk_evaluate_router.post(
    "/bulk",
    response_model=BulkEvaluateResponse,
    summary="Bulk-evaluate many incidents in one request",
    description=(
        "Runs each incident through the exact same pipeline as "
        "POST /api/v1/incidents/evaluate (context aggregation included), "
        "with per-item error isolation -- one malformed incident doesn't "
        "abort the batch, it's just counted as a failure with its error "
        "message. `persist: true` (default) saves every successful "
        "decision exactly like the single-incident endpoint would; "
        "`persist: false` is a pure dry-run bulk simulation, nothing is "
        "written. Returns success/failure counts, priority/risk-band "
        "distribution, and execution-time metrics. Capped at "
        "Settings.bulk_evaluate_max_items incidents per request. Requires "
        "'incidents:evaluate'."
    ),
)
def bulk_evaluate(body: BulkEvaluateRequest, _principal=Depends(require_permission("incidents:evaluate"))):
    incidents_data = [i.model_dump(exclude_none=True) for i in body.incidents]
    try:
        result = bulk_evaluate_use_case.execute(
            incidents_data, persist=body.persist, region=body.region, tenant=body.tenantId,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return bulk_evaluate_result_to_dict(result)


__all__ = ["simulation_router", "bulk_evaluate_router"]
