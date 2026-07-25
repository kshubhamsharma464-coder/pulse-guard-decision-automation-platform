import uuid
from datetime import datetime, timezone
from typing import List, Optional
from app.domain.entities.escalation import EscalationPolicy, EscalationEvent


class EscalationSweep:
    """Design doc §6.7: fires on acknowledgment *silence*, which structurally
    can't be a JsonLogic condition on the incident payload -- there's no
    incident field for "time since assignment with no ack". Walks a policy's
    ordered levels and opens the highest level whose timeout has elapsed
    without an event already recorded for it."""

    def run(
        self,
        decision_id: str,
        policy: EscalationPolicy,
        existing_events: List[EscalationEvent],
        decision_created_at: datetime,
        now: Optional[datetime] = None,
    ) -> Optional[EscalationEvent]:
        now = now or datetime.now(timezone.utc)
        elapsed_minutes = (now - decision_created_at).total_seconds() / 60
        triggered_levels = {e.level for e in existing_events}

        next_level = None
        for level_def in policy.levels:
            if elapsed_minutes >= level_def.timeout_minutes and level_def.level not in triggered_levels:
                next_level = level_def  # keep the furthest level reached, in case the sweep ran infrequently

        if next_level is None:
            return None

        return EscalationEvent(
            id=str(uuid.uuid4()),
            decision_id=decision_id,
            level=next_level.level,
            triggered_at=now,
        )
