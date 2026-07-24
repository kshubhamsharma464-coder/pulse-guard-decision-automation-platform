"""Individual-rule CRUD, always scoped to a Draft rule pack (see
app/application/use_cases/manage_rules.py's module docstring for why a
Rule is never independent of its parent RulePack aggregate, and the
documented linear-scan limitation of get/update/delete/list-by-id)."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.interfaces.api.schemas import (
    CreateRuleRequest, UpdateRuleRequest, RuleResponse, BulkCreateRulesRequest,
    ValidateRuleRequest, ValidationResultResponse,
)
from app.interfaces.api.serializers import rule_to_dict
from app.interfaces.api.security import Principal, require_permission
from app.interfaces.api.dependencies import (
    create_rule_use_case, get_rule_use_case, list_rules_use_case, update_rule_use_case,
    delete_rule_use_case, bulk_create_rules_use_case, validate_rule_use_case, rule_history_use_case,
)

router = APIRouter(prefix="/api/v1/rules", tags=["Rules"])


def _actor(principal: Principal) -> str:
    return principal.subject if principal.is_authenticated else "anonymous"


@router.post("", response_model=RuleResponse, status_code=status.HTTP_201_CREATED, summary="Create a rule")
def create_rule(
    body: CreateRuleRequest,
    rule_pack_id: str = Query(..., alias="rulePackId", description="Draft rule pack this rule belongs to"),
    principal: Principal = Depends(require_permission("rules:edit")),
):
    try:
        rule = create_rule_use_case.execute(rule_pack_id, body.model_dump(), actor=_actor(principal))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return rule_to_dict(rule)


@router.post("/bulk", response_model=List[RuleResponse], status_code=status.HTTP_201_CREATED, summary="Bulk-create rules")
def bulk_create_rules(
    body: BulkCreateRulesRequest,
    rule_pack_id: str = Query(..., alias="rulePackId"),
    principal: Principal = Depends(require_permission("rules:edit")),
):
    try:
        rules = bulk_create_rules_use_case.execute(rule_pack_id, [r.model_dump() for r in body.rules], actor=_actor(principal))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return [rule_to_dict(r) for r in rules]


@router.post("/validate", response_model=ValidationResultResponse, summary="Validate a rule payload")
def validate_rule(body: ValidateRuleRequest):
    result = validate_rule_use_case.execute(body.model_dump())
    return {"isValid": result.is_valid, "errors": result.errors}


@router.get("/history", summary="Rule change history (audit trail)")
def rule_history(
    rule_id: Optional[str] = Query(None, description="Filter to one rule; omit for all rules"),
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    _principal: Principal = Depends(require_permission("rules:read")),
):
    entries = rule_history_use_case.execute(rule_id=rule_id, limit=limit, offset=offset)
    return [
        {
            "id": e.id, "entityId": e.entity_id, "action": e.action, "actor": e.actor,
            "before": e.before, "after": e.after, "reason": e.reason,
            "correlationId": e.correlation_id, "createdAt": e.created_at.isoformat(),
        }
        for e in entries
    ]


@router.get("", response_model=List[RuleResponse], summary="List rules")
def list_rules(
    rule_pack_id: Optional[str] = Query(None, alias="rulePackId"),
    family: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    _principal: Principal = Depends(require_permission("rules:read")),
):
    rules = list_rules_use_case.execute(pack_id=rule_pack_id, family=family, limit=limit, offset=offset)
    return [rule_to_dict(r) for r in rules]


@router.get("/{rule_id}", response_model=RuleResponse, summary="Get a rule by ID")
def get_rule(rule_id: str, _principal: Principal = Depends(require_permission("rules:read"))):
    try:
        rule = get_rule_use_case.execute(rule_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return rule_to_dict(rule)


@router.patch("/{rule_id}", response_model=RuleResponse, summary="Update a rule")
def update_rule(rule_id: str, body: UpdateRuleRequest, principal: Principal = Depends(require_permission("rules:edit"))):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        rule = update_rule_use_case.execute(rule_id, fields, actor=_actor(principal))
    except ValueError as exc:
        code = status.HTTP_404_NOT_FOUND if "No such rule" in str(exc) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(exc))
    return rule_to_dict(rule)


@router.delete("/{rule_id}", response_model=RuleResponse, summary="Soft delete a rule")
def delete_rule(rule_id: str, principal: Principal = Depends(require_permission("rules:edit"))):
    try:
        rule = delete_rule_use_case.execute(rule_id, actor=_actor(principal))
    except ValueError as exc:
        code = status.HTTP_404_NOT_FOUND if "No such rule" in str(exc) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(exc))
    return rule_to_dict(rule)
