from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from app.domain.value_objects.rule_condition import RuleCondition


@dataclass
class Rule:
    rule_code: str
    name: str
    description: str
    family: str
    family_order: int
    priority_weight: int
    severity_band: Optional[str]
    contribution_score: Optional[int]
    conditions: RuleCondition
    exceptions: Optional[RuleCondition]
    conflict_group: Optional[str]
    conflicts_with: List[str]
    is_suppressor: bool
    non_suppressible: bool
    cooldown_minutes: int
    actions: Dict[str, Any]
    mitigations: Dict[str, Any] = field(default_factory=dict)
    sequencing: Optional[Dict[str, Any]] = None
    sla_target: Optional[str] = None
    rule_status: str = "ACTIVE"
    enabled: bool = True

    # Added for the dynamic Rule Management platform -- optional/defaulted,
    # populated when a Rule comes from a Postgres-backed RulePackRepository
    # (rule_to_domain), None for fixture-loaded rules (unaffected).
    id: Optional[str] = None

    def is_active(self) -> bool:
        return self.enabled and self.rule_status == "ACTIVE"
