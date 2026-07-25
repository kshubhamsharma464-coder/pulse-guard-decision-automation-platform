from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class Incident:
    incident_id: str
    payload: Dict[str, Any]
    enriched_context: Dict[str, Any] = field(default_factory=dict)
    degraded_context: bool = False
    # Populated by ContextAggregationService when wired in; 0 means "not
    # measured", in which case the orchestrator falls back to a rough
    # heuristic based on len(enriched_context) for backward compatibility.
    context_sources_total: int = 0
    context_sources_degraded: int = 0

    # Added for the persisted Incident REST resource (POST/GET /api/v1/incidents,
    # docs/rule-management.md) -- optional/defaulted, unused by the
    # evaluation pipeline itself (orchestrator/context aggregation only
    # ever read payload/enriched_context/degraded_context/context_sources_*
    # above), so every pre-existing construction of Incident() is unaffected.
    status: str = "received"  # "received" | "evaluated" | "failed"
    region: Optional[str] = None
    tenant_id: Optional[str] = None
    created_at: Optional[datetime] = None

    def as_evaluation_data(self) -> Dict[str, Any]:
        """Flatten payload to top level, nest enrichment under 'context' --
        matches the rules-seed.json convention (raw incident fields top-level,
        enriched fields as context.*)."""
        data = dict(self.payload)
        data["context"] = self.enriched_context
        return data
