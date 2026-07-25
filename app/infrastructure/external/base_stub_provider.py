from typing import Any, Dict, Optional
from app.domain.interfaces.context_provider import ContextProvider
from app.domain.entities.incident import Incident


class StaticFieldProvider(ContextProvider):
    """Shared base for the STUB providers below: returns a fixed dict of
    default field values, optionally overridden at construction time. This
    demonstrates and exercises the ContextProvider contract before a real
    integration exists -- a real adapter replaces `fetch` with an actual
    HTTP/DB/queue call and keeps the same interface, so nothing above this
    layer (ContextAggregationService, the orchestrator, the API) changes."""

    default_fields: Dict[str, Any] = {}

    def __init__(self, overrides: Optional[Dict[str, Any]] = None):
        self._fields = {**self.default_fields, **(overrides or {})}

    def fetch(self, incident: Incident) -> Dict[str, Any]:
        return dict(self._fields)
