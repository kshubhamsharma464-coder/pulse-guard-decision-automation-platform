from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.entities.audit_log_entry import AuditLogEntry


class AuditLogRepository(ABC):
    """Append-only by contract: no update/delete method is ever exposed
    here. An audit trail that can be edited after the fact isn't one."""

    @abstractmethod
    def save(self, entry: AuditLogEntry) -> AuditLogEntry: ...

    @abstractmethod
    def list_by_entity(self, entity_type: str, entity_id: str) -> List[AuditLogEntry]: ...

    @abstractmethod
    def list_by_entity_type(self, entity_type: str, limit: int = 50, offset: int = 0) -> List[AuditLogEntry]:
        """Every audit entry of a type, newest first, across all entity
        ids -- what GET /api/v1/rules/history (no id filter) reads."""
        ...
