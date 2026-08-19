"""Per-host request pacing with jitter and adaptive backoff."""

from __future__ import annotations

import asyncio
import logging
import random
import time

log = logging.getLogger(__name__)


class Pacer:
    def __init__(
        self, min_interval: float = 2.0, jitter: float = 0.6, max_interval: float = 60.0
    ):
        self.min_interval = max(0.0, min_interval)
        self.jitter = max(0.0, jitter)
        self.max_interval = max_interval
        self._last: dict[str, float] = {}
        self._penalty: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, host: str) -> asyncio.Lock:
        return self._locks.setdefault(host, asyncio.Lock())

    async def wait(self, host: str) -> None:
        async with self._lock(host):
            interval = self.min_interval + self._penalty.get(host, 0.0)
            interval += random.uniform(0, self.jitter)
            elapsed = time.monotonic() - self._last.get(host, 0.0)
            delay = interval - elapsed
            if delay > 0:
                log.debug(
                    "pacing: sleeping %.2fs before next request to %s", delay, host
                )
                await asyncio.sleep(delay)
            self._last[host] = time.monotonic()

    def penalize(self, host: str, seconds: float = 5.0) -> None:
        cur = self._penalty.get(host, 0.0)
        self._penalty[host] = min(self.max_interval, cur + seconds)
        log.warning(
            "pacing: backing off %s -> +%.1fs per request", host, self._penalty[host]
        )

    def relax(self, host: str) -> None:
        cur = self._penalty.get(host, 0.0)
        if cur > 0:
            self._penalty[host] = max(0.0, cur * 0.6 - 0.25)
