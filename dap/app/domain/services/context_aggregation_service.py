from dataclasses import dataclass, field
from typing import Any, Dict, List
from app.domain.entities.incident import Incident
from app.domain.interfaces.context_provider import ContextProvider


@dataclass
class AggregatedContext:
    merged: Dict[str, Any]
    total_sources: int
    degraded_sources: List[str] = field(default_factory=list)

    @property
    def is_degraded(self) -> bool:
        return len(self.degraded_sources) > 0


class ContextAggregationService:
    """Design doc §2/§7: fan out to every registered ContextProvider, merge
    successful results into one dict, and record which sources fell back so
    ConfidenceCalculator can score data completeness. A provider raising or
    timing out degrades that one source only -- never blocks the pipeline."""

    def __init__(self, providers: List[ContextProvider]):
        self.providers = providers

    def aggregate(self, incident: Incident) -> AggregatedContext:
        merged: Dict[str, Any] = {}
        degraded: List[str] = []
        for provider in self.providers:
            try:
                result = provider.fetch(incident) or {}
                merged.update(result)
            except Exception:
                degraded.append(provider.source_name)
        return AggregatedContext(merged=merged, total_sources=len(self.providers), degraded_sources=degraded)
