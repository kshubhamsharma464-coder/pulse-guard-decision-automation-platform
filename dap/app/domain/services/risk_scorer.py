from typing import List, Set, Tuple
from app.domain.entities.rule import Rule

_BANDS = [(30, "LOW"), (50, "MEDIUM"), (75, "HIGH")]


class RiskScorer:
    """Design doc §3c -- additive secondary signal, separate from categorical priority."""

    def score(self, matched: List[Rule], suppressed_codes: Set[str]) -> Tuple[int, str]:
        total = 0
        for rule in matched:
            if rule.rule_code in suppressed_codes:
                continue
            if rule.contribution_score:
                total += rule.contribution_score
        total = max(0, min(total, 120))
        for threshold, band in _BANDS:
            if total <= threshold:
                return total, band
        return total, "CRITICAL"
