from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class EscalationLevel:
    level: str
    timeout_minutes: int


@dataclass
class EscalationPolicy:
    """Design doc §6.7. Levels are evaluated in order; a level fires once
    its timeout has elapsed with no acknowledgment recorded against it."""

    severity_band: str
    levels: List[EscalationLevel] = field(default_factory=list)


@dataclass
class EscalationEvent:
    id: str
    decision_id: str
    level: str
    triggered_at: datetime
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
