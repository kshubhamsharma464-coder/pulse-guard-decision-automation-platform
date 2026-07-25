from abc import ABC, abstractmethod
from typing import List
from app.domain.entities.manual_override import ManualOverride


class ManualOverrideRepository(ABC):
    @abstractmethod
    def save(self, override: ManualOverride) -> ManualOverride: ...

    @abstractmethod
    def list_by_decision(self, decision_id: str) -> List[ManualOverride]: ...
