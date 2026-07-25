from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.entities.decision import Decision


class DecisionRepository(ABC):
    @abstractmethod
    def save(self, decision: Decision) -> Decision: ...

    @abstractmethod
    def get(self, incident_id: str) -> Optional[Decision]: ...

    @abstractmethod
    def list_by_incident(self, incident_id: str) -> List[Decision]: ...

    @abstractmethod
    def list_all(self, limit: int = 100, offset: int = 0) -> List[Decision]:
        """Most-recent-first across every incident -- added for Phase 4's
        decision-distribution analytics (GET /api/v1/decisions/distribution).
        Not used by the hot evaluation/retrieval paths, which stay keyed by
        incident_id via get()/list_by_incident()."""
        ...
