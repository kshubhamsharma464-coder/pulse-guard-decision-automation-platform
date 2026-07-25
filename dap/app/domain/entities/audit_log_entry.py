from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class AuditLogEntry:
    """General-purpose, immutable audit record -- who did what to which
    entity, when, why (via before/after diff), and from where. Distinct
    from ManualOverride (specifically a decision override) and from
    EvaluationHistory (which is just the append-only Decision history) --
    this covers rule/rule-set/user/permission mutations generally."""

    id: str
    entity_type: str      # "rule" | "rule_set" | "decision" | "manual_override" | "user" | ...
    entity_id: str
    action: str            # "created" | "updated" | "activated" | "deprecated" | "rolled_back" | ...
    actor: str              # username, or "system" for autonomous actions
    before: Optional[Dict[str, Any]]
    after: Optional[Dict[str, Any]]
    ip_address: Optional[str]
    request_id: Optional[str]
    correlation_id: Optional[str]
    created_at: datetime
    # Added for the dynamic Rule Management platform's audit requirement
    # ("capture who/when/action/old version/new version/reason/correlation
    # ID") -- optional/defaulted so every pre-existing AuditLogEntry
    # construction is unaffected.
    reason: Optional[str] = None
