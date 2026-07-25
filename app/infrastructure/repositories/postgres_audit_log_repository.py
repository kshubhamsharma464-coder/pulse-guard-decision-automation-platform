from typing import List
from sqlalchemy.orm import sessionmaker
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.entities.audit_log_entry import AuditLogEntry
from app.infrastructure.db.models import AuditLogORM


class PostgresAuditLogRepository(AuditLogRepository):
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def save(self, entry: AuditLogEntry) -> AuditLogEntry:
        with self._session_factory() as session:
            row = AuditLogORM(
                entity_type=entry.entity_type, entity_id=entry.entity_id, action=entry.action,
                actor=entry.actor, before=entry.before, after=entry.after,
                ip_address=entry.ip_address, request_id=entry.request_id,
                correlation_id=entry.correlation_id, created_at=entry.created_at, reason=entry.reason,
            )
            session.add(row)
            session.commit()
            return entry

    def list_by_entity(self, entity_type: str, entity_id: str) -> List[AuditLogEntry]:
        with self._session_factory() as session:
            rows = (
                session.query(AuditLogORM)
                .filter(AuditLogORM.entity_type == entity_type, AuditLogORM.entity_id == entity_id)
                .order_by(AuditLogORM.created_at.asc())
                .all()
            )
            return [self._to_domain(r) for r in rows]

    def list_by_entity_type(self, entity_type: str, limit: int = 50, offset: int = 0) -> List[AuditLogEntry]:
        with self._session_factory() as session:
            rows = (
                session.query(AuditLogORM)
                .filter(AuditLogORM.entity_type == entity_type)
                .order_by(AuditLogORM.created_at.desc())
                .offset(offset).limit(limit)
                .all()
            )
            return [self._to_domain(r) for r in rows]

    @staticmethod
    def _to_domain(r: AuditLogORM) -> AuditLogEntry:
        return AuditLogEntry(
            id=str(r.id), entity_type=r.entity_type, entity_id=r.entity_id, action=r.action,
            actor=r.actor, before=r.before, after=r.after, ip_address=r.ip_address,
            request_id=r.request_id, correlation_id=r.correlation_id, created_at=r.created_at,
            reason=r.reason,
        )
