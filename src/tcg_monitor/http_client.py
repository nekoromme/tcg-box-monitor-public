from __future__ import annotations

import os
import threading
import time
from _thread import LockType
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx


class HttpAttemptsExhausted(RuntimeError):
    """Report how many transport attempts failed within one request budget."""

    def __init__(
        self,
        url: str,
        attempts: int,
        last_error: httpx.HTTPError,
    ) -> None:
        super().__init__(
            f"{type(last_error).__name__} after {attempts} attempt(s): {url}"
        )
        self.url = url
        self.attempts = attempts
        self.last_error = last_error

    @property
    def is_connection_failure(self) -> bool:
        """Whether every retry targeted a host that could not be connected."""

        return isinstance(
            self.last_error,
            (httpx.ConnectError, httpx.ConnectTimeout),
        )


def _request_headers() -> dict[str, str]:
    user_agent = "TCGBoxLotteryMonitor/2.0"
    if contact := os.getenv("MONITOR_USER_AGENT_CONTACT", "").strip():
        user_agent += f" (+{contact})"
    return {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.7",
    }


@dataclass
class FetchResult:
    url: str
    status_code: int
    text: str
    headers: dict[str, str]


@dataclass
class HttpFetcher:
    timeout: float = 20
    max_retries: int = 2
    request_budget_seconds: float = 60
    retry_backoff_seconds: tuple[float, ...] = (0, 0)
    minimum_host_interval: float = 5
    max_bytes: int = 1_000_000
    client: object | None = None
    _last: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _clock: Callable[[], float] = field(default=time.monotonic, repr=False)
    _sleeper: Callable[[float], None] = field(default=time.sleep, repr=False)
    _host_locks: dict[str, LockType] = field(
        default_factory=dict, init=False, repr=False
    )
    _host_locks_guard: LockType = field(
        default_factory=threading.Lock, init=False, repr=False
    )
    _client_guard: LockType = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def __post_init__(self) -> None:
        if self.timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if self.request_budget_seconds <= 0:
            raise ValueError("request_budget_seconds must be greater than zero")
        if self.max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if any(delay < 0 for delay in self.retry_backoff_seconds):
            raise ValueError("retry_backoff_seconds must not contain negative values")

    def _retry_delay(self, attempt_index: int) -> float:
        if not self.retry_backoff_seconds:
            return 0
        return self.retry_backoff_seconds[
            min(attempt_index, len(self.retry_backoff_seconds) - 1)
        ]

    def _host_lock(self, host: str) -> LockType:
        """Return the one lock shared by all requests to the same host.

        Different hosts can be fetched concurrently, while the same provider
        remains strictly sequential.  This keeps rate limiting and the host
        circuit breaker deterministic even when the pipeline uses workers.
        """

        with self._host_locks_guard:
            return self._host_locks.setdefault(host, threading.Lock())

    def _client(self) -> object:
        if self.client is not None:
            return self.client
        with self._client_guard:
            if self.client is None:
                self.client = httpx.Client(follow_redirects=True)
            return self.client

    def fetch(
        self, url: str, etag: str | None = None, last_modified: str | None = None
    ) -> FetchResult:
        host = urlparse(url).netloc
        with self._host_lock(host):
            wait = self.minimum_host_interval - (self._clock() - self._last[host])
            if wait > 0:
                self._sleeper(wait)
            headers = _request_headers()
            if etag:
                headers["If-None-Match"] = etag
            if last_modified:
                headers["If-Modified-Since"] = last_modified
            last_exc: httpx.HTTPError | None = None
            attempts = 0
            client = self._client()
            deadline = self._clock() + self.request_budget_seconds
            for i in range(self.max_retries + 1):
                remaining = deadline - self._clock()
                if remaining <= 0:
                    break
                attempts += 1
                try:
                    r = client.get(  # type: ignore[attr-defined]
                        url,
                        headers=headers,
                        timeout=min(self.timeout, remaining),
                    )
                    self._last[host] = self._clock()
                    text = r.text[: self.max_bytes]
                    return FetchResult(url, r.status_code, text, dict(r.headers))
                except httpx.HTTPError as e:
                    last_exc = e
                    if i == self.max_retries:
                        raise HttpAttemptsExhausted(url, attempts, e) from e
                    remaining = deadline - self._clock()
                    if remaining <= 0:
                        raise HttpAttemptsExhausted(url, attempts, e) from e
                    self._sleeper(min(self._retry_delay(i), remaining))
            if last_exc is not None:
                raise HttpAttemptsExhausted(url, attempts, last_exc) from last_exc
            raise RuntimeError("request budget expired before the first attempt")
