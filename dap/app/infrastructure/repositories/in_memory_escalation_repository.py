from typing import Dict, List
from app.domain.interfaces.escalation_repository import EscalationRepository
from app.domain.entities.escalation import EscalationEvent


class InMemoryEscalationRepository(EscalationRepository):
    def __init__(self):
        self._by_decision: Dict[str, List[EscalationEvent]] = {}

    def save(self, event: EscalationEvent) -> EscalationEvent:
        self._by_decision.setdefault(event.decision_id, []).append(event)
        return event

    def list_by_decision(self, decision_id: str) -> List[EscalationEvent]:
        return list(self._by_decision.get(decision_id, []))
