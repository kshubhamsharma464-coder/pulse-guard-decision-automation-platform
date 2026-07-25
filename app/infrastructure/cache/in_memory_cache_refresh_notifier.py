"""In-process observer implementation -- every subscriber's handler is
called synchronously, in-process, on publish(). Fine for a single-process
deployment; the interface (CacheRefreshNotifier) is what makes swapping
this for a real pub/sub transport later a one-adapter change."""

from typing import Callable, List
from app.domain.interfaces.cache_refresh_notifier import CacheRefreshNotifier, CacheRefreshEvent


class InMemoryCacheRefreshNotifier(CacheRefreshNotifier):
    def __init__(self):
        self._handlers: List[Callable[[CacheRefreshEvent], None]] = []

    def publish(self, event: CacheRefreshEvent) -> None:
        for handler in self._handlers:
            handler(event)

    def subscribe(self, handler: Callable[[CacheRefreshEvent], None]) -> None:
        self._handlers.append(handler)
