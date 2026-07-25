"""Seeds real EscalationPolicy data per severity band, using the level
vocabulary schema.sql already specified (ENGINEER, REGIONAL_MANAGER,
NATIONAL_NOC, VENDOR, OEM -- see the escalation_policies table comment) but
that was never actually instantiated anywhere in the in-memory layer.
Timeouts follow standard NOC acknowledgment-SLA practice: tighter tiers for
higher severity, each level escalating further up the chain the longer an
incident goes unacknowledged. These are starting defaults, not hardcoded
policy -- get_for_severity() is the only place they're defined, so this is
a one-file change if the real numbers need tuning per the ITSM tooling
they'll eventually be imported from."""

from typing import Dict, Optional
from app.domain.interfaces.escalation_policy_repository import EscalationPolicyRepository
from app.domain.entities.escalation import EscalationPolicy, EscalationLevel

_DEFAULT_POLICIES: Dict[str, EscalationPolicy] = {
    "Critical": EscalationPolicy(severity_band="Critical", levels=[
        EscalationLevel(level="ENGINEER", timeout_minutes=5),
        EscalationLevel(level="REGIONAL_MANAGER", timeout_minutes=15),
        EscalationLevel(level="NATIONAL_NOC", timeout_minutes=30),
        EscalationLevel(level="VENDOR", timeout_minutes=60),
        EscalationLevel(level="OEM", timeout_minutes=120),
    ]),
    "High": EscalationPolicy(severity_band="High", levels=[
        EscalationLevel(level="ENGINEER", timeout_minutes=15),
        EscalationLevel(level="REGIONAL_MANAGER", timeout_minutes=30),
        EscalationLevel(level="NATIONAL_NOC", timeout_minutes=60),
        EscalationLevel(level="VENDOR", timeout_minutes=120),
    ]),
    "Medium": EscalationPolicy(severity_band="Medium", levels=[
        EscalationLevel(level="ENGINEER", timeout_minutes=30),
        EscalationLevel(level="REGIONAL_MANAGER", timeout_minutes=90),
    ]),
    "Low": EscalationPolicy(severity_band="Low", levels=[
        EscalationLevel(level="ENGINEER", timeout_minutes=120),
    ]),
}


class InMemoryEscalationPolicyRepository(EscalationPolicyRepository):
    def __init__(self, policies: Optional[Dict[str, EscalationPolicy]] = None):
        self._policies = policies if policies is not None else _DEFAULT_POLICIES

    def get_for_severity(self, severity_band: str) -> Optional[EscalationPolicy]:
        return self._policies.get(severity_band)
