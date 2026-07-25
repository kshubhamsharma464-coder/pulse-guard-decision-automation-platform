from datetime import datetime, timezone
from typing import List
from app.domain.entities.decision import Decision

_SEVERITY_ORDER = ["Low", "Medium", "High", "Critical"]


def _parse_duration_minutes(value: str) -> int:
    if not value:
        return 10**6
    parts = value.lower().split()
    n = int(parts[0])
    return n * 60 if "hour" in value.lower() else n


class SlaBreachSweep:
    """Design doc §6: a scheduled job, not a request-time rule. Checks open
    decisions against their targetSLA; once `threshold_fraction` of the
    target window has elapsed with no resolution, bumps priority one level
    and flags for supervisor notification. Wire to APScheduler/Celery
    beat/cron in production; `run()` is called directly here and from tests
    for now -- the scheduling mechanism is separate from the sweep logic."""

    def __init__(self, threshold_fraction: float = 0.8):
        self.threshold_fraction = threshold_fraction

    def run(self, open_decisions: List[Decision], now: datetime = None) -> List[str]:
        now = now or datetime.now(timezone.utc)
        bumped: List[str] = []
        for decision in open_decisions:
            if decision.resolved or not decision.priority:
                continue
            target = decision.actions.get("targetSLA")
            if not target:
                continue

            elapsed_minutes = (now - decision.created_at).total_seconds() / 60
            target_minutes = _parse_duration_minutes(target)
            if elapsed_minutes < target_minutes * self.threshold_fraction:
                continue
            if decision.priority not in _SEVERITY_ORDER:
                continue

            idx = _SEVERITY_ORDER.index(decision.priority)
            if idx < len(_SEVERITY_ORDER) - 1:
                decision.priority = _SEVERITY_ORDER[idx + 1]
                decision.actions["priority"] = decision.priority
                decision.actions["supervisorNotified"] = True
                bumped.append(decision.incident_id)
        return bumped
