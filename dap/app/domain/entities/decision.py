from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class MatchedRuleTrace:
    rule_code: str
    name: str
    family: str
    priority_weight: int
    severity_band: Optional[str]
    contribution_score: Optional[int]


@dataclass
class RejectedRuleTrace:
    rule_code: str
    name: str
    reason: str


@dataclass
class Decision:
    incident_id: str
    priority: Optional[str]
    risk_score: int
    risk_band: str
    actions: Dict[str, Any]
    mitigations: Dict[str, Any]
    execution_plan: List[Dict[str, Any]]
    matched_rules: List[MatchedRuleTrace]
    rejected_rules: List[RejectedRuleTrace]
    suppressed_rules: List[Dict[str, Any]]
    compliance_constraints: List[Dict[str, Any]]
    confidence_score: float
    degraded_context: bool
    explanation: str
    engine_version: str = "0.1.0"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved: bool = False  # set True once the incident is closed; SLA sweep skips resolved decisions
