"""AI-assisted rule authoring and decision narration -- non-authoritative
by construction (docs/ai-assist.md). Every endpoint here either returns a
draft that still requires an explicit, separately-permissioned human
action to take effect (generate-rule), or read-only prose that never
touches the decision/rule data itself (document-rule, explain-decision).

Errors from the configured AI provider (timeout, malformed response, HTTP
failure -- app/infrastructure/ai/common.py's AIProviderError) surface as
502 Bad Gateway, never silently swallowed into a fabricated success."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.interfaces.api.schemas import (
    GenerateRuleRequest, GenerateRuleResponse, DocumentRuleRequest, DocumentRuleResponse, ExplainDecisionResponse,
)
from app.interfaces.api.security import Principal, require_permission
from app.interfaces.api.dependencies import (
    generate_rule_from_description_use_case, document_rule_use_case, explain_decision_ai_use_case,
    get_rule_use_case, decision_repository, settings,
)
from app.interfaces.api.serializers import rule_to_dict
from app.infrastructure.ai.common import AIProviderError

router = APIRouter(prefix="/api/v1/ai", tags=["AI"])


@router.post(
    "/generate-rule", response_model=GenerateRuleResponse,
    summary="Generate a rule from natural language description",
    description=(
        "Drafts a rule payload from a plain-language description. Returned as a DRAFT only -- "
        "nothing is persisted. Review `rule` and `validationErrors`, then POST the (possibly "
        "edited) result to /api/v1/rules yourself. The AI never creates, publishes, or activates "
        "anything on its own."
    ),
)
def generate_rule(body: GenerateRuleRequest, principal: Principal = Depends(require_permission("rules:edit"))):
    try:
        result = generate_rule_from_description_use_case.execute(
            description=body.description, family=body.family, region=body.region, sample_payload=body.samplePayload,
        )
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI provider error: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {
        "rule": result.rule, "isValid": result.validation.is_valid,
        "validationErrors": result.validation.errors, "aiProvider": settings.ai_provider,
    }


@router.post(
    "/document-rule", response_model=DocumentRuleResponse,
    summary="Generate human-readable documentation for a rule",
    description="Provide either `ruleId` (an existing rule) or an inline `rule` payload.",
)
def document_rule(body: DocumentRuleRequest, principal: Principal = Depends(require_permission("rules:read"))):
    if body.ruleId:
        try:
            rule = rule_to_dict(get_rule_use_case.execute(body.ruleId))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    elif body.rule:
        rule = body.rule.model_dump()
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide either 'ruleId' or 'rule'")

    try:
        documentation = document_rule_use_case.execute(rule)
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI provider error: {exc}")
    return {"documentation": documentation, "aiProvider": settings.ai_provider}


@router.post(
    "/explain-decision/{incident_id}", response_model=ExplainDecisionResponse,
    summary="AI-assisted plain-language explanation of a decision",
    description=(
        "Narrates an ALREADY-COMPUTED decision in plain language, for a non-technical reader. "
        "Strictly additive to the deterministic `explanation` every decision already carries -- "
        "this endpoint cannot change the decision, only describe it."
    ),
)
def explain_decision(incident_id: str, principal: Principal = Depends(require_permission("decisions:read"))):
    decision = decision_repository.get(incident_id)
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No decision found for incident '{incident_id}'")
    try:
        ai_explanation = explain_decision_ai_use_case.execute(decision)
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI provider error: {exc}")
    return {
        "incidentId": incident_id, "deterministicExplanation": decision.explanation,
        "aiExplanation": ai_explanation, "aiProvider": settings.ai_provider,
    }
