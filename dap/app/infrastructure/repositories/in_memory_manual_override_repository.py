from typing import Dict, List
from app.domain.interfaces.manual_override_repository import ManualOverrideRepository
from app.domain.entities.manual_override import ManualOverride


class InMemoryManualOverrideRepository(ManualOverrideRepository):
    def __init__(self):
        self._by_decision: Dict[str, List[ManualOverride]] = {}

    def save(self, override: ManualOverride) -> ManualOverride:
        self._by_decision.setdefault(override.decision_id, []).append(override)
        return override

    def list_by_decision(self, decision_id: str) -> List[ManualOverride]:
        return list(self._by_decision.get(decision_id, []))
