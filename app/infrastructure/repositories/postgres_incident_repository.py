from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import sessionmaker
from app.domain.interfaces.incident_repository import IncidentRepository
from app.domain.entities.incident import Incident
from app.infrastructure.db.models import IncidentORM
from app.infrastructure.db.mappers import incident_to_domain, incident_to_orm


class PostgresIncidentRepository(IncidentRepository):
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def save(self, incident: Incident) -> Incident:
        if incident.created_at is None:
            incident.created_at = datetime.now(timezone.utc)
        with self._session_factory() as session:
            existing = session.get(IncidentORM, incident.incident_id)
            if existing is not None:
                existing.payload = incident.payload
                existing.enriched_context = incident.enriched_context
                existing.degraded_context = incident.degraded_context
                existing.context_sources_total = incident.context_sources_total
                existing.context_sources_degraded = incident.context_sources_degraded
                existing.status = incident.status
                existing.region = incident.region
                session.commit()
                return incident
            row = incident_to_orm(incident)
            session.add(row)
            session.commit()
            return incident

    def get(self, incident_id: str) -> Optional[Incident]:
        with self._session_factory() as session:
            row = session.get(IncidentORM, incident_id)
            return incident_to_domain(row) if row else None

    def list_all(self, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Incident]:
        with self._session_factory() as session:
            query = session.query(IncidentORM)
            if status is not None:
                query = query.filter(IncidentORM.status == status)
            rows = query.order_by(IncidentORM.created_at.desc()).offset(offset).limit(limit).all()
            return [incident_to_domain(r) for r in rows]
