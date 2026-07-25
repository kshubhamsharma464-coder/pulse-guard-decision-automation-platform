"""Rule pack lifecycle -- create/import/export/list/get/patch/delete,
publish, activate, rollback. See docs/rule-management.md for the full
Draft -> Published -> Active -> Deprecated/Archived state machine and the
Editor (rules:edit) vs Policy Admin (rules:publish/activate/rollback/
delete) permission split."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.interfaces.api.schemas import (
    CreateRulePackRequest, UpdateRulePackRequest, ImportRulePackRequest, RulePackResponse,
    RollbackRulePackRequest, ActivateRulePackRequest, DeleteRulePackRequest, ErrorResponse,
)
from app.interfaces.api.serializers import rule_pack_to_dict
from app.interfaces.api.security import Principal, require_permission
from app.interfaces.api.dependencies import (
    create_rule_pack_use_case, update_rule_pack_metadata_use_case, soft_delete_rule_pack_use_case,
    publish_rule_pack_use_case, activate_rule_pack_use_case, rollback_rule_pack_use_case,
    import_rule_pack_use_case, export_rule_pack_use_case, rule_pack_repository,
)
from app.application.use_cases.rule_pack_lifecycle import _rule_from_json

router = APIRouter(prefix="/api/v1/rule-packs", tags=["Rule Packs"])


def _actor(principal: Principal) -> str:
    return principal.subject if principal.is_authenticated else "anonymous"


@router.post("/import", response_model=RulePackResponse, status_code=status.HTTP_201_CREATED, summary="Import rule pack from JSON")
def import_rule_pack(body: ImportRulePackRequest, principal: Principal = Depends(require_permission("rules:edit"))):
    document = body.model_dump()
    document["rules"] = [r for r in document.pop("rules", [])]
    try:
        pack = import_rule_pack_use_case.execute(document, actor=_actor(principal))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return rule_pack_to_dict(pack)


@router.post("", response_model=RulePackResponse, status_code=status.HTTP_201_CREATED, summary="Create rule pack")
def create_rule_pack(body: CreateRulePackRequest, principal: Principal = Depends(require_permission("rules:edit"))):
    rules = [_rule_from_json(r.model_dump()) for r in body.rules]
    pack = create_rule_pack_use_case.execute(
        name=body.name, region=body.region, tenant_id=body.tenantId, rules=rules, actor=_actor(principal),
    )
    return rule_pack_to_dict(pack)


@router.get("/active", response_model=RulePackResponse, summary="Return active version")
def get_active_rule_pack(
    name: str = Query(..., description="Rule pack name"),
    region: Optional[str] = Query(None),
    _principal: Principal = Depends(require_permission("rules:read")),
):
    pack = rule_pack_repository.get_active(name, region=region)
    if pack is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No active rule pack named '{name}' for region={region!r}")
    return rule_pack_to_dict(pack)


@router.get("", response_model=List[RulePackResponse], summary="List rule packs")
def list_rule_packs(
    status_filter: Optional[str] = Query(None, alias="status"),
    region: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _principal: Principal = Depends(require_permission("rules:read")),
):
    packs = rule_pack_repository.list_all(status=status_filter, region=region, limit=limit, offset=offset)
    return [rule_pack_to_dict(p) for p in packs]


@router.get("/{pack_id}", response_model=RulePackResponse, summary="Rule pack details")
def get_rule_pack(pack_id: str, _principal: Principal = Depends(require_permission("rules:read"))):
    pack = rule_pack_repository.get_by_id(pack_id)
    if pack is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No such rule pack: {pack_id}")
    return rule_pack_to_dict(pack)


@router.get("/{pack_id}/export", summary="Export a rule pack's active version as JSON")
def export_rule_pack(pack_id: str, _principal: Principal = Depends(require_permission("rules:read"))):
    pack = rule_pack_repository.get_by_id(pack_id)
    if pack is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No such rule pack: {pack_id}")
    try:
        return export_rule_pack_use_case.execute(pack.name, region=pack.region)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.patch("/{pack_id}", response_model=RulePackResponse, summary="Update metadata")
def update_rule_pack(pack_id: str, body: UpdateRulePackRequest, principal: Principal = Depends(require_permission("rules:edit"))):
    fields = {k: v for k, v in {"name": body.name, "region": body.region, "tenant_id": body.tenantId}.items() if v is not None}
    try:
        pack = update_rule_pack_metadata_use_case.execute(
            pack_id, actor=_actor(principal), expected_lock_version=body.expectedLockVersion, **fields,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return rule_pack_to_dict(pack)


@router.delete("/{pack_id}", response_model=RulePackResponse, summary="Soft delete")
def delete_rule_pack(pack_id: str, body: DeleteRulePackRequest = DeleteRulePackRequest(), principal: Principal = Depends(require_permission("rules:delete"))):
    try:
        pack = soft_delete_rule_pack_use_case.execute(
            pack_id, actor=_actor(principal), reason=body.reason, expected_lock_version=body.expectedLockVersion,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return rule_pack_to_dict(pack)


@router.post("/{pack_id}/publish", response_model=RulePackResponse, summary="Publish")
def publish_rule_pack(pack_id: str, principal: Principal = Depends(require_permission("rules:publish"))):
    try:
        pack = publish_rule_pack_use_case.execute(pack_id, actor=_actor(principal))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return rule_pack_to_dict(pack)


@router.post("/{pack_id}/activate", response_model=RulePackResponse, summary="Activate")
def activate_rule_pack(pack_id: str, body: ActivateRulePackRequest = ActivateRulePackRequest(), principal: Principal = Depends(require_permission("rules:activate"))):
    try:
        pack = activate_rule_pack_use_case.execute(
            pack_id, actor=_actor(principal), reason=body.reason, expected_lock_version=body.expectedLockVersion,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return rule_pack_to_dict(pack)


@router.post("/{pack_id}/rollback", response_model=RulePackResponse, summary="Rollback")
def rollback_rule_pack(pack_id: str, body: RollbackRulePackRequest = RollbackRulePackRequest(), principal: Principal = Depends(require_permission("rules:rollback"))):
    pack = rule_pack_repository.get_by_id(pack_id)
    if pack is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No such rule pack: {pack_id}")
    try:
        rolled_back = rollback_rule_pack_use_case.execute(
            pack.name, pack.version, actor=_actor(principal), reason=body.reason,
            expected_lock_version=body.expectedLockVersion,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return rule_pack_to_dict(rolled_back)
