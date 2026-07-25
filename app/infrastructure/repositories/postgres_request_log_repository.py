from sqlalchemy.orm import sessionmaker
from app.domain.interfaces.request_log_repository import RequestLogRepository
from app.domain.entities.request_log_entry import RequestLogEntry
from app.infrastructure.db.models import RequestLogORM


class PostgresRequestLogRepository(RequestLogRepository):
    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def save(self, entry: RequestLogEntry) -> RequestLogEntry:
        with self._session_factory() as session:
            row = RequestLogORM(
                method=entry.method, path=entry.path, status_code=entry.status_code,
                duration_ms=entry.duration_ms, request_id=entry.request_id,
                correlation_id=entry.correlation_id, ip_address=entry.ip_address,
                created_at=entry.created_at,
            )
            session.add(row)
            session.commit()
            return entry
