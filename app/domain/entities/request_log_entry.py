from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RequestLogEntry:
    """HTTP-request-level log record -- distinct from AuditLogEntry
    (business-entity mutations) and from structured stdout logs (which stay
    in the log aggregator, not the database). Written by RequestLoggingMiddleware."""

    id: str
    method: str
    path: str
    status_code: int
    duration_ms: float
    request_id: str
    correlation_id: Optional[str]
    ip_address: Optional[str]
    created_at: datetime
