from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.entities.incident import Incident


class IncidentRepository(ABC):
    """Persisted Incident resources -- POST /api/v1/incidents creates one,
    GET /api/v1/incidents/{id} and GET /api/v1/incidents read them back.
    Distinct from DecisionRepository: an Incident is the submitted request;
    a Decision is the pipeline's output for it. Keyed by incident_id (the
    caller-supplied business identifier), not a separate surrogate id --
    same convention EscalationEvent/ManualOverride use for decision_id."""

    @abstractmethod
    def save(self, incident: Incident) -> Incident: ...

    @abstractmethod
    def get(self, incident_id: str) -> Optional[Incident]: ...

    @abstractmethod
    def list_all(self, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Incident]: ...
