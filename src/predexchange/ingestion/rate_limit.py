"""Token-bucket rate limiter for REST APIs (e.g. Kalshi). Backoff on 429."""

from __future__ import annotations

import time
from threading import Lock


class TokenBucket:
    """Simple token bucket: refill rate per second, max burst."""

    def __init__(self, rate: float = 10.0, capacity: int | None = None) -> None:
        self.rate = rate
        self.capacity = capacity or int(rate * 2)
        self.tokens = float(self.capacity)
        self.last = time.monotonic()
        self._lock = Lock()

    def consume(self, n: int = 1) -> bool:
        """Consume n tokens. Return True if allowed, False if not enough."""
        with self._lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
            self.last = now
            if self.tokens >= n:
                self.tokens -= n
                return True
            return False

    def wait_for_token(self, n: int = 1) -> None:
        """Block until n tokens available."""
        while not self.consume(n):
            time.sleep(0.1)


def backoff_on_429(retries: int = 3, base_delay: float = 1.0) -> float:
    """Return delay in seconds for next retry after a 429. Exponential backoff."""
    return base_delay * (2 ** retries)
