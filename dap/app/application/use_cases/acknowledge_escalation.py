from datetime import datetime, timezone
from app.domain.entities.escalation import EscalationEvent


class AcknowledgeEscalationUseCase:
    """Records who acknowledged an escalation event and when. Refuses to
    silently re-acknowledge -- if it's already acknowledged, that's a bug in
    the caller, not something to paper over."""

    def execute(self, event: EscalationEvent, acknowledged_by: str) -> EscalationEvent:
        if event.acknowledged_at is not None:
            raise ValueError(f"Escalation event {event.id} was already acknowledged by {event.acknowledged_by}")
        if not acknowledged_by or not acknowledged_by.strip():
            raise ValueError("Acknowledging an escalation requires an identified acknowledger")
        event.acknowledged_at = datetime.now(timezone.utc)
        event.acknowledged_by = acknowledged_by
        return event
