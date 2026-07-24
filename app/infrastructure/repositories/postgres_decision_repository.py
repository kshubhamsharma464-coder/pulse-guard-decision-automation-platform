"""Postgres-backed DecisionRepository. Append-only, same semantics as
InMemoryDecisionRepository: get() returns the most recent decision for an
incident_id, list_by_incident() returns full history in insertion order."""

from typing import List, Optional
from sqlalchemy.orm import sessionmaker
from app.domain.interfaces.decision_repository import DecisionRepository
from app.domain.entities.decision import Decision
from app.infrastructure.db.models import DecisionORM
from app.infrastructure.db.mappers import decision_to_domain, decision_to_orm


class PostgresDecisionRepository(DecisionRepository):
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def save(self, decision: Decision) -> Decision:
        with self._session_factory() as session:
            row = decision_to_orm(decision)
            session.add(row)
            session.commit()
            return decision

    def get(self, incident_id: str) -> Optional[Decision]:
        with self._session_factory() as session:
            row = (
                session.query(DecisionORM)
                .filter(DecisionORM.incident_id == incident_id)
                .order_by(DecisionORM.created_at.desc())
                .first()
            )
            return decision_to_domain(row) if row else None

    def list_by_incident(self, incident_id: str) -> List[Decision]:
        with self._session_factory() as session:
            rows = (
                session.query(DecisionORM)
                .filter(DecisionORM.incident_id == incident_id)
                .order_by(DecisionORM.created_at.asc())
                .all()
            )
            return [decision_to_domain(r) for r in rows]

    def list_all(self, limit: int = 100, offset: int = 0) -> List[Decision]:
        with self._session_factory() as session:
            rows = (
                session.query(DecisionORM)
                .order_by(DecisionORM.created_at.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )
            return [decision_to_domain(r) for r in rows]
