from typing import List
from sqlalchemy.orm import sessionmaker
from app.domain.interfaces.manual_override_repository import ManualOverrideRepository
from app.domain.entities.manual_override import ManualOverride
from app.infrastructure.db.models import ManualOverrideORM
from app.infrastructure.db.mappers import manual_override_to_domain, manual_override_to_orm


class PostgresManualOverrideRepository(ManualOverrideRepository):
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def save(self, override: ManualOverride) -> ManualOverride:
        with self._session_factory() as session:
            row = manual_override_to_orm(override)
            session.add(row)
            session.commit()
            return override

    def list_by_decision(self, decision_id: str) -> List[ManualOverride]:
        with self._session_factory() as session:
            rows = (
                session.query(ManualOverrideORM)
                .filter(ManualOverrideORM.decision_id == decision_id)
                .order_by(ManualOverrideORM.created_at.asc())
                .all()
            )
            return [manual_override_to_domain(r) for r in rows]
