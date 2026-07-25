from abc import ABC, abstractmethod
from typing import Any, Dict
from app.domain.entities.incident import Incident


class ContextProvider(ABC):
    """Port for one Context Aggregation Layer source (design doc §2's source
    table). Each provider is independently fallible -- raising here degrades
    just this one source, it never blocks the others or the decision itself."""

    source_name: str

    @abstractmethod
    def fetch(self, incident: Incident) -> Dict[str, Any]:
        ...
