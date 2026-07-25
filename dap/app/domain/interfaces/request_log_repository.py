from abc import ABC, abstractmethod
from app.domain.entities.request_log_entry import RequestLogEntry


class RequestLogRepository(ABC):
    @abstractmethod
    def save(self, entry: RequestLogEntry) -> RequestLogEntry: ...
