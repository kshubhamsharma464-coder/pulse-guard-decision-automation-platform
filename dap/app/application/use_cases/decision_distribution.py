"""Phase 4 decision distribution analytics (GET /api/v1/decisions/distribution):
aggregate stats over recent persisted decisions -- counts by priority and
risk band, average risk/confidence scores, degraded-context rate. Read-only,
computed over whatever DecisionRepository.list_all() returns; the
aggregation itself is application-layer logic (not pushed into the
repository) so it stays identical regardless of which backend (in-memory or
Postgres) is behind DecisionRepository."""

from dataclasses import dataclass, field
from typing import Dict

from app.domain.interfaces.decision_repository import DecisionRepository


@dataclass
class DistributionResult:
    total_decisions: int
    priority_distribution: Dict[str, int] = field(default_factory=dict)
    risk_band_distribution: Dict[str, int] = field(default_factory=dict)
    average_risk_score: float = 0.0
    average_confidence_score: float = 0.0
    degraded_context_count: int = 0


class DecisionDistributionUseCase:
    def __init__(self, decision_repository: DecisionRepository):
        self.decision_repository = decision_repository

    def execute(self, limit: int = 10_000) -> DistributionResult:
        decisions = self.decision_repository.list_all(limit=limit, offset=0)
        if not decisions:
            return DistributionResult(total_decisions=0)

        priority_distribution: Dict[str, int] = {}
        risk_band_distribution: Dict[str, int] = {}
        degraded_count = 0
        risk_sum = 0
        confidence_sum = 0.0

        for decision in decisions:
            priority_key = decision.priority or "Unknown"
            priority_distribution[priority_key] = priority_distribution.get(priority_key, 0) + 1
            risk_band_distribution[decision.risk_band] = risk_band_distribution.get(decision.risk_band, 0) + 1
            if decision.degraded_context:
                degraded_count += 1
            risk_sum += decision.risk_score
            confidence_sum += decision.confidence_score

        total = len(decisions)
        return DistributionResult(
            total_decisions=total,
            priority_distribution=priority_distribution,
            risk_band_distribution=risk_band_distribution,
            average_risk_score=risk_sum / total,
            average_confidence_score=confidence_sum / total,
            degraded_context_count=degraded_count,
        )
