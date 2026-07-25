"""DistributedCacheBackend -- the shared, cross-replica cache layer that
sits between RuleCache's local per-process TTL cache and PostgreSQL (the
source of truth). Redis is the only concrete implementation today
(app/infrastructure/cache/redis_cache_backend.py's RedisCacheBackend);
this interface is what keeps that swappable (Memcached, Hazelcast, a
different Redis client library) without RuleCache -- or anything above
it, including the Decision Engine -- ever changing. Same Strategy-pattern
discipline as AIProvider (Phase 3) and CacheRefreshNotifier (Phase 2.5).

Both methods are deliberately failure-swallowing by contract (never raise
for connectivity problems, only return None / silently no-op) -- this
distributed layer is a performance optimization RuleCache falls through
around, never a dependency RuleCache's correctness relies on. See
RuleCache's own docstring for the full L1 (local) -> L2 (this) -> L3
(Postgres) fallback chain and docs/policy-platform.md for the failure
strategy this implements."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class DistributedCacheBackend(ABC):
    @abstractmethod
    def read_active(self, key: str) -> Optional[Dict[str, Any]]:
        """Returns the currently-active snapshot for `key`, or None if
        nothing has been published yet, or if the backend itself is
        unreachable. Callers must treat both cases identically (fall back
        to the source of truth) -- that's why this never raises for a
        connectivity failure, only ever returns None."""
        ...

    @abstractmethod
    def write_active(self, key: str, snapshot: Dict[str, Any]) -> None:
        """Atomically publish `snapshot` as the new active value for
        `key`, replacing whatever was active before it -- see
        RedisCacheBackend's docstring for exactly how "atomic" is
        achieved with Redis specifically. Never raises for connectivity
        failures (best-effort write-through): callers must not depend on
        this succeeding for correctness, only for performance and
        cross-replica propagation."""
        ...

    @abstractmethod
    def ping(self) -> bool:
        """Cheap connectivity/health check. Used by the readiness probe
        and by failure-strategy decisions -- never called on the hot
        read/write path itself."""
        ...
