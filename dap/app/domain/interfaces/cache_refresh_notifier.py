"""Observer-pattern abstraction for "something changed, caches should
refresh" -- the single interface every rule/rule-pack mutation use case
publishes through, and every cache subscribes to. Swapping the in-memory
implementation (InMemoryCacheRefreshNotifier) for Postgres LISTEN/NOTIFY,
Redis pub/sub, or Kafka later is a new adapter behind this same interface
-- no use case or cache changes. Per docs/rule-management.md: an in-memory
bus is the explicitly-sanctioned current implementation, not a shortcut."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional


@dataclass
class CacheRefreshEvent:
    entity_type: str  # "rule_pack" | "rule"
    entity_id: Optional[str]
    action: str        # "published" | "activated" | "rolled_back" | "deleted" | "updated"
    metadata: Dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CacheRefreshNotifier(ABC):
    @abstractmethod
    def publish(self, event: CacheRefreshEvent) -> None: ...

    @abstractmethod
    def subscribe(self, handler: Callable[[CacheRefreshEvent], None]) -> None: ...
