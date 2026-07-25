from datetime import datetime, timezone
from typing import Dict, List, Optional
from app.domain.interfaces.incident_repository import IncidentRepository
from app.domain.entities.incident import Incident


class InMemoryIncidentRepository(IncidentRepository):
    def __init__(self):
        self._by_id: Dict[str, Incident] = {}

    def save(self, incident: Incident) -> Incident:
        if incident.created_at is None:
            incident.created_at = datetime.now(timezone.utc)
        self._by_id[incident.incident_id] = incident
        return incident

    def get(self, incident_id: str) -> Optional[Incident]:
        return self._by_id.get(incident_id)

    def list_all(self, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Incident]:
        incidents = list(self._by_id.values())
        if status is not None:
            incidents = [i for i in incidents if i.status == status]
        incidents.sort(key=lambda i: i.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return incidents[offset: offset + limit]
