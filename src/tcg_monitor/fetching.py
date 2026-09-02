from __future__ import annotations

import re
import threading
import time
from _thread import LockType
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from tcg_monitor.http_client import HttpAttemptsExhausted, HttpFetcher
from tcg_monitor.models import RenderMode, SourceConfig

BrowserFetcher = Callable[[str, str | None, int], str]


class PageKind(StrEnum):
    CONTENT = "content"
    EMPTY = "empty"
    JAVASCRIPT_SHELL = "javascript_shell"
    CHALLENGE = "challenge"
    LOGIN = "login"


@dataclass(frozen=True)
class PageResult:
    url: str
    html: str
    status_code: int | None
    fetch_method: str
    headers: dict[str, str] = field(default_factory=dict)
    not_modified: bool = False
    duration_ms: int = 0


class FetchProblem(RuntimeError):
    def __init__(
        self,
        url: str,
        reason: str,
        *,
        status_code: int | None = None,
        fetch_method: str = "http",
        blocked: bool = False,
        cause_code: str | None = None,
        attempts: int | None = None,
    ) -> None:
        super().__init__(reason)
        self.url = url
        self.reason = reason
        self.status_code = status_code
        self.fetch_method = fetch_method
        self.blocked = blocked
        self.cause_code = cause_code
        self.attempts = attempts
        self.duration_ms = 0


class CircuitOpenError(FetchProblem):
    def __init__(self, url: str, cause: CircuitCause | None = None) -> None:
        super().__init__(
            url,
            "host_circuit_open",
            status_code=cause.status_code if cause else None,
            fetch_method="skipped_circuit_open",
            blocked=True,
            cause_code=cause.code if cause else None,
            attempts=cause.attempts if cause else None,
        )


def provider_host(url: str) -> str:
    host = urlsplit(url).netloc.casefold()
    for prefix in ("www.", "ww.", "w.", "mobile."):
        if host.startswith(prefix):
            return host.removeprefix(prefix)
    return host


@dataclass
class CircuitCause:
    code: str
    status_code: int | None = None
    attempts: int | None = None


@dataclass
class HostCircuitBreaker:
    threshold: int = 2
    _blocked_streaks: dict[str, int] = field(default_factory=dict)
    _open_hosts: set[str] = field(default_factory=set)
    _open_causes: dict[str, CircuitCause] = field(default_factory=dict)
    _lock: LockType = field(default_factory=threading.Lock, init=False, repr=False)

    def ensure_available(self, url: str) -> None:
        with self._lock:
            host = provider_host(url)
            if host in self._open_hosts:
                raise CircuitOpenError(url, self._open_causes.get(host))

    def record_success(self, url: str) -> None:
        with self._lock:
            self._blocked_streaks[provider_host(url)] = 0

    def record_blocked(
        self,
        url: str,
        occurrences: int = 1,
        *,
        cause_code: str = "blocked_response",
        status_code: int | None = None,
        attempts: int | None = None,
    ) -> bool:
        if occurrences < 1:
            raise ValueError("occurrences must be greater than zero")
        host = provider_host(url)
        with self._lock:
            count = self._blocked_streaks.get(host, 0) + occurrences
            self._blocked_streaks[host] = count
            if count >= self.threshold:
                self._open_hosts.add(host)
                self._open_causes[host] = CircuitCause(
                    cause_code,
                    status_code,
                    attempts if attempts is not None else count,
                )
                return True
            return False

    def is_open(self, url: str) -> bool:
        with self._lock:
            return provider_host(url) in self._open_hosts

    @property
    def open_hosts(self) -> set[str]:
        with self._lock:
            return set(self._open_hosts)


_CHALLENGE_MARKERS = (
    "cf-chl-",
    "checking your browser",
    "attention required",
    "cloudflare ray id",
    "captcha",
    "recaptcha",
    "hcaptcha",
    "画像認証",
    "アクセス確認",
    "人間であることを確認",
    "verify that you're not a robot",
    "verify you are not a robot",
)
_LOGIN_MARKERS = (
    "ログインしてください",
    "ログインが必要です",
    "sign in to continue",
    "please log in",
)
_LOGIN_HEADING_MARKERS = (
    "ログイン",
    "サインイン",
    "sign in",
    "log in",
    "login",
)
_JAVASCRIPT_MARKERS = (
    "javascriptを有効にしてください",
    "javascript is required",
    "enable javascript",
    "このページを表示するにはjavascript",
)


def _looks_like_login_page(soup: BeautifulSoup, text: str) -> bool:
    """Distinguish an access gate from a normal shop page with a login widget.

    Large commerce pages often keep a hidden password form in the common
    header.  Treating every password input as an access gate caused otherwise
    usable storefronts (for example EDION) to be discarded.  A real login
    replacement is either compact, or identifies itself as login in the page
    title/main heading.
    """

    folded_text = text.casefold()
    has_login_message = any(marker in folded_text for marker in _LOGIN_MARKERS)
    password_input = soup.find(
        "input",
        attrs={"type": re.compile(r"^password$", re.I)},
    )
    if not has_login_message and password_input is None:
        return False

    primary_container = (
        soup.find("main")
        or soup.select_one("[role='main']")
        or soup.select_one("#main")
        or soup.select_one("#contents")
    )
    primary_headings = (
        primary_container.find_all(["h1", "h2"], limit=5)
        if primary_container is not None
        else soup.find_all("h1", limit=3)
    )
    heading_text = " ".join(
        node.get_text(" ", strip=True)
        for node in [
            soup.title,
            *primary_headings,
        ]
        if node is not None
    ).casefold()
    heading_is_login = any(
        marker in heading_text for marker in _LOGIN_HEADING_MARKERS
    )
    return heading_is_login or len(text) < 2_000


def classify_page(html: str) -> PageKind:
    folded = html.casefold()
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    has_challenge_marker = any(
        marker in folded for marker in _CHALLENGE_MARKERS
    )
    has_definite_challenge = any(
        marker in folded
        for marker in ("cf-chl-", "cloudflare ray id", "checking your browser")
    )
    if has_challenge_marker and (has_definite_challenge or len(text) < 1_000):
        return PageKind.CHALLENGE
    if _looks_like_login_page(soup, text):
        return PageKind.LOGIN

    if not text and not soup.find("img", src=True):
        return PageKind.EMPTY
    if (
        len(text) < 500
        and any(marker in text.casefold() for marker in _JAVASCRIPT_MARKERS)
    ):
        return PageKind.JAVASCRIPT_SHELL
    if len(text) < 80 and soup.find("script") and (
        soup.select_one("#root:empty")
        or soup.select_one("#app:empty")
        or "__next_data__" in folded
        or "__nuxt__" in folded
    ):
        return PageKind.JAVASCRIPT_SHELL
    return PageKind.CONTENT


def browser_wait_selector(source: SourceConfig) -> str | None:
    if source.render_wait_selector:
        return source.render_wait_selector
    for values in source.selectors.values():
        for value in values:
            selector = value.strip()
            if selector:
                return selector
    return None


@dataclass
class PageFetcher:
    http_fetcher: HttpFetcher
    browser_fetcher: BrowserFetcher
    circuit_breaker: HostCircuitBreaker = field(default_factory=HostCircuitBreaker)
    timeout_ms: int = 30_000
    conditional_get: bool = True
    _host_locks: dict[str, LockType] = field(
        default_factory=dict, init=False, repr=False
    )
    _host_locks_guard: LockType = field(
        default_factory=threading.Lock, init=False, repr=False
    )
    _cache_lock: LockType = field(
        default_factory=threading.Lock, init=False, repr=False
    )
    _browser_lock: LockType = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def _host_lock(self, url: str) -> LockType:
        host = provider_host(url)
        with self._host_locks_guard:
            return self._host_locks.setdefault(host, threading.Lock())

    def _cached_record(
        self, cache: MutableMapping[str, object], url: str
    ) -> dict[str, object]:
        if not self.conditional_get:
            return {}
        with self._cache_lock:
            cached = cache.get(url)
        return cached if isinstance(cached, dict) else {}

    def _update_cache(
        self,
        cache: MutableMapping[str, object],
        url: str,
        record: dict[str, object],
    ) -> None:
        if not self.conditional_get:
            return
        with self._cache_lock:
            cache[url] = record

    def _browser(
        self,
        url: str,
        source: SourceConfig,
        *,
        status_code: int | None = None,
    ) -> PageResult:
        self.circuit_breaker.ensure_available(url)
        try:
            # A GitHub-hosted runner has little memory.  Keep heavyweight
            # Chromium launches sequential while ordinary HTTP hosts continue
            # in parallel in other workers.
            with self._browser_lock:
                html = self.browser_fetcher(
                    url,
                    browser_wait_selector(source),
                    self.timeout_ms,
                )
        except CircuitOpenError:
            raise
        except Exception as exc:
            raise FetchProblem(
                url,
                f"browser_fetch_failed:{type(exc).__name__}",
                status_code=status_code,
                fetch_method="playwright",
                cause_code=type(exc).__name__,
            ) from exc

        kind = classify_page(html)
        if kind in {PageKind.CHALLENGE, PageKind.LOGIN}:
            opened = self.circuit_breaker.record_blocked(
                url,
                cause_code=kind.value,
                status_code=status_code,
            )
            reason = "host_circuit_open" if opened else kind.value
            raise FetchProblem(
                url,
                reason,
                status_code=status_code,
                fetch_method="playwright",
                blocked=True,
                cause_code=kind.value,
                attempts=self.circuit_breaker.threshold if opened else None,
            )
        if kind in {PageKind.EMPTY, PageKind.JAVASCRIPT_SHELL}:
            raise FetchProblem(
                url,
                kind.value,
                status_code=status_code,
                fetch_method="playwright",
            )
        selector = source.render_wait_selector
        if selector and not BeautifulSoup(html, "lxml").select_one(selector):
            raise FetchProblem(
                url,
                "expected_rendered_content_missing",
                status_code=status_code,
                fetch_method="playwright",
            )
        self.circuit_breaker.record_success(url)
        return PageResult(url, html, status_code, "playwright")

    def fetch(
        self,
        url: str,
        source: SourceConfig,
        cache: MutableMapping[str, object],
        *,
        browser_url: str | None = None,
    ) -> PageResult:
        # The lock covers HTTP/browser acquisition *and* classification.  If a
        # blocked response opens the circuit, the next same-host request sees
        # that state before it can touch the network.
        started = time.monotonic()
        with self._host_lock(url):
            try:
                result = self._fetch_locked(
                    url,
                    source,
                    cache,
                    browser_url=browser_url,
                )
            except FetchProblem as problem:
                problem.duration_ms = round((time.monotonic() - started) * 1_000)
                raise
        return replace(
            result,
            duration_ms=round((time.monotonic() - started) * 1_000),
        )

    def _fetch_locked(
        self,
        url: str,
        source: SourceConfig,
        cache: MutableMapping[str, object],
        *,
        browser_url: str | None = None,
    ) -> PageResult:
        """Fetch one public page according to the source's common render policy.

        Security challenges and login screens are never passed to Playwright as
        a bypass attempt.  Browser rendering is reserved for ordinary
        JavaScript shells and explicitly configured Playwright sources.
        """

        self.circuit_breaker.ensure_available(url)
        if source.render_mode == RenderMode.PLAYWRIGHT:
            return self._browser(browser_url or url, source)

        use_conditional_get = self.conditional_get and not bool(
            source.parser_options.get("disable_conditional_get", False)
        )
        cached_record = self._cached_record(cache, url) if use_conditional_get else {}
        etag = cached_record.get("etag")
        last_modified = cached_record.get("last_modified")
        try:
            response = self.http_fetcher.fetch(
                url,
                etag=str(etag) if etag else None,
                last_modified=str(last_modified) if last_modified else None,
            )
        except HttpAttemptsExhausted as exc:
            if (
                source.render_mode
                == RenderMode.HTTP_THEN_BROWSER_ONCE_NO_CHALLENGE_BYPASS
                and isinstance(exc.last_error, httpx.ReadTimeout)
            ):
                # A read timeout is an ordinary transport failure, not evidence
                # of a security challenge. The explicitly configured browser
                # path may render the same public page once. 403/429, login,
                # challenge, and connection failures remain forbidden here.
                return self._browser(browser_url or url, source)
            opened = (
                self.circuit_breaker.record_blocked(
                    url,
                    occurrences=exc.attempts,
                    cause_code=type(exc.last_error).__name__,
                    attempts=exc.attempts,
                )
                if exc.is_connection_failure
                else False
            )
            reason = (
                "host_circuit_open"
                if opened
                else f"http_fetch_failed:{type(exc.last_error).__name__}"
            )
            raise FetchProblem(
                url,
                reason,
                fetch_method="http",
                blocked=exc.is_connection_failure,
                cause_code=type(exc.last_error).__name__,
                attempts=exc.attempts,
            ) from exc
        except Exception as exc:
            raise FetchProblem(
                url,
                f"http_fetch_failed:{type(exc).__name__}",
                fetch_method="http",
                cause_code=type(exc).__name__,
            ) from exc

        now = datetime.now(UTC).isoformat()
        status = response.status_code
        if status == 304:
            self.circuit_breaker.record_success(url)
            cached_record["checked_at"] = now
            if use_conditional_get:
                self._update_cache(cache, url, cached_record)
            return PageResult(
                url,
                "",
                status,
                "http_conditional_not_modified",
                response.headers,
                not_modified=True,
            )

        kind = classify_page(response.text)
        if status >= 400:
            blocked = status in {403, 429} or kind in {
                PageKind.CHALLENGE,
                PageKind.LOGIN,
            }
            cause_code = (
                kind.value
                if kind in {PageKind.CHALLENGE, PageKind.LOGIN}
                else f"http_status_{status}"
            )
            opened = (
                self.circuit_breaker.record_blocked(
                    url,
                    cause_code=cause_code,
                    status_code=status,
                )
                if blocked
                else False
            )
            if not blocked:
                self.circuit_breaker.record_success(url)
            if opened:
                reason = "host_circuit_open"
            elif kind in {PageKind.CHALLENGE, PageKind.LOGIN}:
                reason = kind.value
            else:
                reason = f"http_status_{status}"
            raise FetchProblem(
                url,
                reason,
                status_code=status,
                fetch_method="http",
                blocked=blocked,
                cause_code=cause_code if blocked else None,
                attempts=self.circuit_breaker.threshold if opened else None,
            )

        if (
            kind == PageKind.CONTENT
            and source.render_mode == RenderMode.HTTP_THEN_PLAYWRIGHT_IF_EMPTY
            and source.render_wait_selector
            and not BeautifulSoup(response.text, "lxml").select_one(
                source.render_wait_selector
            )
        ):
            kind = PageKind.EMPTY
        if kind in {PageKind.CHALLENGE, PageKind.LOGIN}:
            opened = self.circuit_breaker.record_blocked(
                url,
                cause_code=kind.value,
                status_code=status,
            )
            reason = "host_circuit_open" if opened else kind.value
            raise FetchProblem(
                url,
                reason,
                status_code=status,
                fetch_method="http",
                blocked=True,
                cause_code=kind.value,
                attempts=self.circuit_breaker.threshold if opened else None,
            )
        if kind == PageKind.CONTENT:
            self.circuit_breaker.record_success(url)
            if use_conditional_get:
                self._update_cache(
                    cache,
                    url,
                    {
                        "etag": response.headers.get("etag")
                        or response.headers.get("ETag"),
                        "last_modified": response.headers.get("last-modified")
                        or response.headers.get("Last-Modified"),
                        "checked_at": now,
                    },
                )
            return PageResult(url, response.text, status, "http", response.headers)

        self.circuit_breaker.record_success(url)
        if source.render_mode.browser_fallback_enabled:
            return self._browser(
                browser_url or url,
                source,
                status_code=status,
            )
        raise FetchProblem(
            url,
            kind.value,
            status_code=status,
            fetch_method="http",
        )


__all__ = [
    "BrowserFetcher",
    "CircuitOpenError",
    "FetchProblem",
    "HostCircuitBreaker",
    "PageFetcher",
    "PageKind",
    "PageResult",
    "classify_page",
    "provider_host",
]
