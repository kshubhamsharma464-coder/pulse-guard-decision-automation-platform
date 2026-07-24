"""Rule-pack cache invalidation -- the decision flagged as open in an earlier
draft of tradeoffs.md #17 is now made explicit here:

CHOSEN: push-based invalidation is primary, short TTL is the fallback safety
net. On `RulePackRepository.activate()`, the composition root calls
`RulePackCache.invalidate()` directly (in-process now; a real multi-replica
deployment publishes the same event over Postgres LISTEN/NOTIFY so every
replica invalidates immediately instead of waiting out a TTL). The TTL below
exists purely as a safety net for a replica that missed the notification
(e.g. reconnecting after a network blip) -- it is deliberately short (10s)
because the scenario that matters most here (R017, a rule pack published in
response to an active incident storm) is exactly the moment a multi-second
propagation gap is least acceptable.
"""

import time
from typing import Any, Callable, Optional


class TTLCache:
    def __init__(self, ttl_seconds: float = 10.0):
        self.ttl_seconds = ttl_seconds
        self._value: Optional[Any] = None
        self._loaded_at: float = 0.0

    def get(self, loader: Callable[[], Any]) -> Any:
        now = time.monotonic()
        if self._value is None or (now - self._loaded_at) > self.ttl_seconds:
            self._value = loader()
            self._loaded_at = now
        return self._value

    def invalidate(self) -> None:
        """Called synchronously on rule-pack activation (push path). In a
        multi-replica deployment this is also triggered by a Postgres
        LISTEN/NOTIFY (or Redis pub/sub) handler on every replica, not just
        the one that performed the activation."""
        self._value = None
        self._loaded_at = 0.0

    def set(self, value: Any) -> None:
        """Atomically install an already-computed value as the current
        cache entry -- added for Phase 5's RuleCache.refresh(), which
        builds the new value fully (from PostgreSQL, then best-effort
        write-through to Redis) BEFORE calling this, rather than
        invalidating first and lazily reloading on the next get(). A
        plain attribute assignment is atomic under the GIL, so a
        concurrent get() from another thread either sees the old value
        completely or the new one completely -- never a torn state --
        without needing an explicit lock."""
        self._value = value
        self._loaded_at = time.monotonic()

    def peek(self) -> Optional[Any]:
        """Read whatever is currently cached without triggering a load,
        and without considering TTL staleness -- for read-only status/
        health reporting (RuleCache.status(), the readiness probe) that
        must never have the side effect of causing a reload."""
        return self._value

    # -- Aliases matching the Rule Management platform's cache vocabulary
    # (docs/rule-management.md) -- reload()/refresh()/warmup() are the same
    # mechanism as get()/invalidate() above, named for the three call sites
    # that use them (RuleCache): warmup() at startup, refresh() after a
    # mutation, reload() to force a synchronous reload right now.

    def warmup(self, loader: Callable[[], Any]) -> Any:
        """Eager-load if not already warm. No-op if already cached --
        startup calls this once; it never forces a redundant reload."""
        return self.get(loader)

    def refresh(self, loader: Callable[[], Any]) -> Any:
        """Force a synchronous reload right now, bypassing TTL -- used
        after a rule/rule-pack mutation so the very next request sees it,
        without waiting for the TTL fallback."""
        self.invalidate()
        return self.get(loader)

    def reload(self) -> None:
        """Invalidate without eagerly reloading -- the next get() call
        loads lazily. This is what a LISTEN/NOTIFY or Redis pub/sub handler
        on a *different* replica than the one that made the change would
        call (it doesn't have the new value to eagerly load with; it just
        needs to stop serving the stale one)."""
        self.invalidate()
