from abc import ABC, abstractmethod
from typing import List
from app.domain.entities.escalation import EscalationEvent


class EscalationRepository(ABC):
    @abstractmethod
    def save(self, event: EscalationEvent) -> EscalationEvent: ...

    @abstractmethod
    def list_by_decision(self, decision_id: str) -> List[EscalationEvent]: ...
