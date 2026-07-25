from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict


@dataclass
class ManualOverride:
    """Design doc §6.6: an operator override is a separate, fully audited
    record. The automated decision it references is never mutated."""

    id: str
    decision_id: str
    operator: str
    original_decision: Dict[str, Any]
    override_decision: Dict[str, Any]
    reason: str
    created_at: datetime
