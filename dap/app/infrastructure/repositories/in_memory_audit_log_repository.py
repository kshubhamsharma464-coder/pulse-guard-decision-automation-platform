from typing import Dict, List, Tuple
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.entities.audit_log_entry import AuditLogEntry


class InMemoryAuditLogRepository(AuditLogRepository):
    def __init__(self):
        self._by_entity: Dict[Tuple[str, str], List[AuditLogEntry]] = {}

    def save(self, entry: AuditLogEntry) -> AuditLogEntry:
        self._by_entity.setdefault((entry.entity_type, entry.entity_id), []).append(entry)
        return entry

    def list_by_entity(self, entity_type: str, entity_id: str) -> List[AuditLogEntry]:
        return list(self._by_entity.get((entity_type, entity_id), []))

    def list_by_entity_type(self, entity_type: str, limit: int = 50, offset: int = 0) -> List[AuditLogEntry]:
        entries = [e for (etype, _), entries in self._by_entity.items() if etype == entity_type for e in entries]
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries[offset: offset + limit]
