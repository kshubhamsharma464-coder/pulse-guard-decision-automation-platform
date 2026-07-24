from typing import Dict, List, Optional
from app.domain.interfaces.decision_repository import DecisionRepository
from app.domain.entities.decision import Decision


class InMemoryDecisionRepository(DecisionRepository):
    """In-memory stand-in for the `decisions` table. Keeps full history per
    incident_id, since a context change after incident creation produces a
    new, linked decision rather than mutating the original (design doc §7)."""

    def __init__(self):
        self._by_incident: Dict[str, List[Decision]] = {}

    def save(self, decision: Decision) -> Decision:
        self._by_incident.setdefault(decision.incident_id, []).append(decision)
        return decision

    def get(self, incident_id: str) -> Optional[Decision]:
        history = self._by_incident.get(incident_id)
        return history[-1] if history else None

    def list_by_incident(self, incident_id: str) -> List[Decision]:
        return list(self._by_incident.get(incident_id, []))

    def all(self) -> List[Decision]:
        return [d for history in self._by_incident.values() for d in history]

    def list_all(self, limit: int = 100, offset: int = 0) -> List[Decision]:
        ordered = sorted(self.all(), key=lambda d: d.created_at, reverse=True)
        return ordered[offset: offset + limit]
