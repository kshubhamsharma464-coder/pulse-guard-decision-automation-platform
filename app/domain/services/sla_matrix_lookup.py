from typing import Any, Dict, Optional

_PRIORITY_TO_SEVERITY = {
    "Critical": "SEV1_CRITICAL",
    "High": "SEV2_MAJOR",
    "Medium": "SEV3_MINOR",
    "Low": "SEV4_INFORMATIONAL",
}


class SlaMatrixLookup:
    """Looks up default response/resolution targets from the
    customer_sla_rules_telecom pack's slaMatrix (customerTier x severity).

    Used only to FILL IN targetSLA when no rule has already set one
    explicitly -- an explicit rule (e.g. R004's Gold-tier 15-minute target,
    or SLA-RULE-008's 5-minute emergency target) always wins over the
    matrix default. This keeps the matrix as a fallback data source, not a
    competing rule, so it can never override something a rule already
    decided -- consistent with the "score never overrides category"
    reasoning in tradeoffs.md #4."""

    def __init__(self, matrix: Dict[str, Dict[str, Dict[str, int]]]):
        self.matrix = matrix

    def resolve(self, customer_tier: Optional[str], priority: Optional[str]) -> Optional[Dict[str, Any]]:
        if not customer_tier or not priority:
            return None
        severity = _PRIORITY_TO_SEVERITY.get(priority)
        if severity is None:
            return None
        tier_row = self.matrix.get(customer_tier.upper())
        if not tier_row:
            return None
        return tier_row.get(severity)
