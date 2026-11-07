"""Per-process request and SSE capacity guards.

Deployment must use a shared rate limiter before increasing worker/process count.
"""

import asyncio
import time
from collections import defaultdict, deque

from app.core.config import Settings


class RequestRateLimiter:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._settings: Settings | None = None

    async def allow(self, key: str, settings: Settings) -> bool:
        async with self._lock:
            if self._settings is not settings:
                self._buckets.clear()
                self._settings = settings
            now = time.monotonic()
            bucket = self._buckets[key]
            cutoff = now - settings.api_rate_limit_window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= settings.api_rate_limit_requests:
                return False
            bucket.append(now)
            return True


class SSEConnectionLimiter:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.active = 0

    async def acquire(self, limit: int) -> bool:
        async with self._lock:
            if self.active >= limit:
                return False
            self.active += 1
            return True

    async def release(self) -> None:
        async with self._lock:
            self.active -= 1
