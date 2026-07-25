from typing import Any, Dict, List
from app.domain.entities.rule import Rule
from app.domain.entities.decision import MatchedRuleTrace, RejectedRuleTrace


class ExplainabilityBuilder:
    def build(self, matched: List[Rule], rejected: List[RejectedRuleTrace],
              suppressed: List[Dict[str, Any]], risk_score: int, risk_band: str,
              final_actions: Dict[str, Any]) -> str:
        if not matched:
            return "No rules matched; incident routed to manual review."
        reasons = "; ".join(f"{r.name} ({r.rule_code})" for r in matched)
        priority = final_actions.get("priority", "Unclassified")
        return (
            f"{priority} because: {reasons}. Risk score {risk_score} ({risk_band} band) "
            f"reflects combined signal weight and is used for triage ranking only, "
            f"not as the priority driver."
        )

    def matched_trace(self, matched: List[Rule]) -> List[MatchedRuleTrace]:
        return [
            MatchedRuleTrace(r.rule_code, r.name, r.family, r.priority_weight, r.severity_band, r.contribution_score)
            for r in matched
        ]
