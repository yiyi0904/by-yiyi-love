"""全局下载限速（令牌桶）。"""

from __future__ import annotations

import threading
import time


class GlobalRateLimiter:
    """所有任务共享的限速器；rate_bps <= 0 表示不限速。"""

    def __init__(self, rate_bps: int = 0) -> None:
        self._lock = threading.Lock()
        self._rate = max(0, int(rate_bps))
        self._tokens = 0.0
        self._last = time.monotonic()

    @property
    def rate(self) -> int:
        with self._lock:
            return self._rate

    def set_rate(self, rate_bps: int) -> None:
        with self._lock:
            self._rate = max(0, int(rate_bps))
            self._tokens = 0.0
            self._last = time.monotonic()

    def consume(self, amount: int) -> None:
        """消费 amount 字节，必要时阻塞以维持速率。"""
        if amount <= 0:
            return
        while True:
            with self._lock:
                rate = self._rate
                if rate <= 0:
                    return
                now = time.monotonic()
                self._tokens = min(
                    float(rate),
                    self._tokens + (now - self._last) * rate,
                )
                self._last = now
                if self._tokens >= amount:
                    self._tokens -= amount
                    return
                deficit = amount - self._tokens
                wait = deficit / rate
                self._tokens = 0.0
            time.sleep(min(max(wait, 0.01), 0.5))
