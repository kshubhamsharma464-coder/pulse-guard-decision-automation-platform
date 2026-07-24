from typing import List
from app.domain.interfaces.request_log_repository import RequestLogRepository
from app.domain.entities.request_log_entry import RequestLogEntry


class InMemoryRequestLogRepository(RequestLogRepository):
    def __init__(self):
        self._entries: List[RequestLogEntry] = []

    def save(self, entry: RequestLogEntry) -> RequestLogEntry:
        self._entries.append(entry)
        return entry
