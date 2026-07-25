from abc import ABC, abstractmethod
from typing import Optional
from app.domain.entities.escalation import EscalationPolicy


class EscalationPolicyRepository(ABC):
    """New interface -- the EscalationSweep job and EscalationPolicy/
    EscalationEvent entities already existed (design doc §6.7), but no
    concrete policy data was ever seeded anywhere, and there was no
    repository/lookup port to fetch a policy by severity band. Without
    this, EscalationSweep.run() had nothing to walk: it always returns
    None because it's never handed a real EscalationPolicy. This closes
    that gap -- the acknowledgment-SLA auto-escalation mechanism was fully
    built but not actually usable end-to-end until now."""

    @abstractmethod
    def get_for_severity(self, severity_band: str) -> Optional[EscalationPolicy]: ...
