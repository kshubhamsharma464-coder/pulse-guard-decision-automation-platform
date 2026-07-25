from typing import List
from sqlalchemy.orm import sessionmaker
from app.domain.interfaces.escalation_repository import EscalationRepository
from app.domain.entities.escalation import EscalationEvent
from app.infrastructure.db.models import EscalationEventORM
from app.infrastructure.db.mappers import escalation_event_to_domain, escalation_event_to_orm


class PostgresEscalationRepository(EscalationRepository):
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def save(self, event: EscalationEvent) -> EscalationEvent:
        with self._session_factory() as session:
            row = escalation_event_to_orm(event)
            session.add(row)
            session.commit()
            return event

    def list_by_decision(self, decision_id: str) -> List[EscalationEvent]:
        with self._session_factory() as session:
            rows = (
                session.query(EscalationEventORM)
                .filter(EscalationEventORM.decision_id == decision_id)
                .order_by(EscalationEventORM.triggered_at.asc())
                .all()
            )
            return [escalation_event_to_domain(r) for r in rows]
