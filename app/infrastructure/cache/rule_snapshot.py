"""JSON-serializable snapshot of a RulePack for the distributed (Redis)
cache layer. Reuses rule_pack_lifecycle.py's `_rule_to_json`/`_rule_from_json`
(the exact same per-rule JSON shape POST /api/v1/rules and rule-pack
export/import already use) rather than inventing a second serialization
format -- manage_rules.py already imports these two functions
cross-module for the same reason (see its own top-of-file docstring)."""

from datetime import datetime
from typing import Any, Dict

from app.domain.entities.rule_pack import RulePack
from app.application.use_cases.rule_pack_lifecycle import _rule_to_json, _rule_from_json


def rule_pack_to_snapshot(pack: RulePack) -> Dict[str, Any]:
    return {
        "id": pack.id,
        "name": pack.name,
        "version": pack.version,
        "status": pack.status,
        "region": pack.region,
        "tenantId": pack.tenant_id,
        "createdBy": pack.created_by,
        "parentVersion": pack.parent_version,
        "createdAt": pack.created_at.isoformat() if pack.created_at else None,
        "activatedAt": pack.activated_at.isoformat() if pack.activated_at else None,
        "rules": [_rule_to_json(r) for r in pack.rules],
    }


def rule_pack_from_snapshot(data: Dict[str, Any]) -> RulePack:
    def _parse(value):
        return datetime.fromisoformat(value) if value else None

    return RulePack(
        id=data.get("id"),
        name=data["name"],
        version=data["version"],
        status=data["status"],
        region=data.get("region"),
        tenant_id=data.get("tenantId"),
        created_by=data.get("createdBy", "system"),
        parent_version=data.get("parentVersion"),
        created_at=_parse(data.get("createdAt")),
        activated_at=_parse(data.get("activatedAt")),
        rules=[_rule_from_json(r) for r in data.get("rules", [])],
    )
