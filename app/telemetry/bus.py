"""In-process pub/sub for security events.

Every block (L1 or L2) and every pass that survives both layers publishes a
compact event to the bus. Subscribers — currently the dashboard's
`GET /api/alerts/stream` SSE endpoint — each get their own bounded
`asyncio.Queue`. On backpressure (subscriber falls behind), the oldest event
is dropped: it's better to skip a frame than to grow memory unboundedly.

This is intentionally single-process. For a multi-replica deployment, swap
the in-process queue for Redis Pub/Sub or NATS while keeping the
`subscribe()` / `publish()` shape identical.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class AlertBus:
    QUEUE_MAX = 200  # per subscriber

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self.QUEUE_MAX)
        async with self._lock:
            self._subscribers.add(q)
        logger.debug("bus subscriber added (n=%d)", len(self._subscribers))
        return q

    async def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            self._subscribers.discard(q)
        logger.debug("bus subscriber removed (n=%d)", len(self._subscribers))

    def publish(self, event: dict[str, Any]) -> None:
        """Fire-and-forget broadcast to all subscribers.

        Synchronous so callers don't have to await. Each subscriber gets the
        event via its own queue. If a queue is full, drop the oldest item to
        keep memory bounded — the stream is live telemetry, not durable.
        """
        event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        for q in list(self._subscribers):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # should not happen given the drop above

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
