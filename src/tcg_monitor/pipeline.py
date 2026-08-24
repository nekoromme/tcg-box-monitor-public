from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from tcg_monitor.browser_fetch import fetch_rendered_html, pokemon_release_window_url
from tcg_monitor.config import load_config
from tcg_monitor.fetching import (
    BrowserFetcher,
    CircuitOpenError,
    FetchProblem,
    HostCircuitBreaker,
    PageFetcher,
    PageResult,
    provider_host,
)
from tcg_monitor.http_client import HttpFetcher
from tcg_monitor.models import (
    Alert,
    Config,
    GameSupport,
    LotteryCase,
    Release,
    SourceConfig,
)
from tcg_monitor.ocr import read_image_text
from tcg_monitor.parsers.dragonball_official import (
    discover_dragonball_official_store_urls,
    is_dragonball_official_store_index,
    parse_dragonball_official_products,
    parse_dragonball_official_store_lottery,
)
from tcg_monitor.parsers.furuichi import (
    discover_furuichi_lottery_urls,
    furuichi_index_has_target_lottery,
    is_furuichi_news_index,
    is_furuichi_source,
    parse_furuichi_lottery_detail,
)
from tcg_monitor.parsers.generic import (
    discover_geo_news_urls,
    is_geo_news_index,
    parse_generic,
    parse_onepiece_topics,
)
from tcg_monitor.parsers.local_lottery import (
    discover_livepocket_event_urls,
    is_livepocket_search_page,
    is_livepocket_source,
    is_yahoo_realtime_source,
    parse_curated_store_campaign,
    parse_hobby_station_source,
    parse_livepocket_event,
    parse_yahoo_realtime,
    yahoo_realtime_page_loaded,
    yahoo_repair_discovery_urls,
)
from tcg_monitor.parsers.lorcana_official import (
    discover_lorcana_product_urls,
    is_lorcana_product_index,
    parse_lorcana_official_product,
)
from tcg_monitor.parsers.official_retailers import (
    KONAMI_STYLE_SOURCE,
    ONEPIECE_SHOP_SOURCE,
    PREMIUM_BANDAI_DB_SOURCE,
    TAKARATOMY_MALL_SOURCE,
    discover_official_retailer_urls,
    is_official_retailer_index,
    is_official_retailer_source,
    official_retailer_index_should_have_links,
    parse_official_retailer_detail,
)
from tcg_monitor.parsers.onepiece_official import parse_onepiece_official_products
from tcg_monitor.parsers.pokemon_center import (
    discover_pokemon_center_news_urls,
    is_pokemon_center_news_index,
    parse_pokemon_center_lottery,
)
from tcg_monitor.parsers.pokemon_official_products import parse_pokemon_official_products
from tcg_monitor.parsers.premium_bandai import (
    parse_nyuka_now_lottery_summary,
    parse_nyuka_now_premium_bandai,
)
from tcg_monitor.parsers.retailer_lottery import (
    discover_retailer_lottery_urls,
    is_retailer_lottery_index,
    is_retailer_lottery_source,
    parse_retailer_lottery_detail,
    retailer_lottery_index_error,
)
from tcg_monitor.parsers.snkrdunk import (
    discover_snkrdunk_article_urls,
    is_snkrdunk_schedule_page,
    parse_snkrdunk,
)
from tcg_monitor.parsers.tsutaya_line import (
    is_tsutaya_line_form_url,
    parse_tsutaya_line_form,
    tsutaya_line_form_urls,
)
from tcg_monitor.parsers.yugioh_official import parse_yugioh_official_products
from tcg_monitor.source_priority import merge_lotteries, merge_releases
from tcg_monitor.state import MonitorState


@dataclass
class SourceMetrics:
    source_id: str
    last_fetch_at: str | None = None
    http_status: int | None = None
    fetch_method: str | None = None
    duration_ms: int = 0
    fetched_pages: int = 0
    parsed_count: int = 0
    excluded_count: int = 0
    last_error: str | None = None
    failure_cause: str | None = None
    failure_attempts: int | None = None
    fetch_duration_ms: int = 0

    def fetched(self, result: PageResult) -> None:
        self.last_fetch_at = datetime.now(UTC).isoformat()
        self.http_status = result.status_code
        self.fetch_method = result.fetch_method
        self.fetched_pages += 1
        self.fetch_duration_ms += result.duration_ms

    def failed(self, problem: FetchProblem) -> None:
        skipped = problem.fetch_method == "skipped_circuit_open"
        if not skipped:
            self.last_fetch_at = datetime.now(UTC).isoformat()
            self.fetched_pages += 1
            self.fetch_duration_ms += problem.duration_ms
        # When a circuit is already open, keep the actual response that opened
        # it instead of replacing HTTP 403/429 or the transport cause with an
        # empty "skipped" result.  A source whose first request was skipped
        # still receives the shared host cause carried by CircuitOpenError.
        if not skipped or self.last_error is None:
            self.http_status = problem.status_code
            self.fetch_method = problem.fetch_method
            self.last_error = problem.reason
            self.failure_cause = problem.cause_code
            self.failure_attempts = problem.attempts

    def as_state(self) -> dict[str, object]:
        return {
            "last_fetch_at": self.last_fetch_at,
            "http_status": self.http_status,
            "fetch_method": self.fetch_method,
            "duration_ms": self.duration_ms,
            "fetched_pages": self.fetched_pages,
            "parsed_count": self.parsed_count,
            "excluded_count": self.excluded_count,
            "last_error": self.last_error,
            "failure_cause": self.failure_cause,
            "failure_attempts": self.failure_attempts,
            "fetch_duration_ms": self.fetch_duration_ms,
        }


@dataclass(frozen=True)
class _PrefetchRequest:
    source: SourceConfig
    url: str


class _RootPrefetcher:
    """Keep one primary request in flight per provider host.

    The main pipeline still parses and saves one source at a time, preserving
    deterministic state updates and parser dependencies.  Only the idle
    network wait is overlapped.  A host's next source is not scheduled until
    the current source (including fallback/discovered pages) is finished, so
    circuit-breaker decisions stay ordered.
    """

    def __init__(
        self,
        sources: list[SourceConfig],
        max_workers: int,
        fetch_page: Callable[[SourceConfig, str], PageResult],
    ) -> None:
        self._fetch_page = fetch_page
        self._executor = (
            ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="monitor-host",
            )
            if max_workers > 1
            else None
        )
        self._queues: dict[str, deque[_PrefetchRequest]] = {}
        self._source_hosts: dict[str, str] = {}
        self._futures: dict[tuple[str, str], Future[PageResult]] = {}

        if self._executor is None:
            return
        for source in sources:
            if not source.discovery_urls:
                continue
            url = source.discovery_urls[0]
            host = provider_host(url)
            self._source_hosts[source.id] = host
            self._queues.setdefault(host, deque()).append(
                _PrefetchRequest(source, url)
            )
        for host in self._queues:
            self._schedule_next(host)

    def _schedule_next(self, host: str) -> None:
        if self._executor is None:
            return
        queue = self._queues.get(host)
        if not queue:
            return
        request = queue.popleft()
        self._futures[(request.source.id, request.url)] = self._executor.submit(
            self._fetch_page,
            request.source,
            request.url,
        )

    def take(self, source: SourceConfig, url: str) -> PageResult | None:
        future = self._futures.pop((source.id, url), None)
        return future.result() if future is not None else None

    def source_done(self, source: SourceConfig) -> None:
        host = self._source_hosts.get(source.id)
        if host is not None:
            self._schedule_next(host)

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True)


def _parser_for(source: SourceConfig):  # type: ignore[no-untyped-def]
    source_id = source.id
    if source_id == "pokemon_official_products":
        return parse_pokemon_official_products
    if source_id == "onepiece_official_products":
        return parse_onepiece_official_products
    if source_id == "dragonball_official_products":
        return parse_dragonball_official_products
    if source_id == "dragonball_official_store":
        return parse_dragonball_official_store_lottery
    if source_id == "yugioh_official_products":
        return parse_yugioh_official_products
    if source_id == "lorcana_official_products":
        return parse_lorcana_official_product
    if is_official_retailer_source(source_id):
        return parse_official_retailer_detail
    if source_id in {"onepiece_official_topics", "premium_bandai_onepiece"}:
        return parse_onepiece_topics
    if source_id == "livepocket_hobby_station":
        return parse_hobby_station_source
    if is_livepocket_source(source):
        return parse_livepocket_event
    if source_id in {"pokemon_center_online", "pokemon_center_store"}:
        return parse_pokemon_center_lottery
    if is_yahoo_realtime_source(source):
        return parse_yahoo_realtime
    if source.parser_kind == "curated_store_campaign":
        return parse_curated_store_campaign
    if is_furuichi_source(source_id):
        return parse_furuichi_lottery_detail
    if source_id == "nyuka_now_premium_bandai_onepiece":
        return parse_nyuka_now_premium_bandai
    if source_id == "nyuka_now_fullcomp_livepocket":
        return parse_nyuka_now_lottery_summary
    if source_id in {"snkrdunk_pokemon", "snkrdunk_onepiece"}:
        return parse_snkrdunk
    if is_retailer_lottery_source(source):
        return parse_retailer_lottery_detail
    return parse_generic


def _alert(
    source_id: str,
    name: str,
    url: str,
    reason: str,
    summary: str,
    status: int | None = None,
) -> Alert:
    return Alert(
        None,
        source_id,
        url,
        name,
        [],
        reason,
        summary,
        status,
        url,
    ).with_fingerprint()


def _fixture_path(fixture_dir: str, source_id: str, url: str) -> Path:
    url_parts = urlsplit(url)
    if url_parts.netloc.casefold().removeprefix("www.") in {
        "livepocket.jp",
        "t.livepocket.jp",
    } and url_parts.path.startswith("/e/"):
        slug = url_parts.path.removeprefix("/e/").strip("/")
        if slug:
            return Path(fixture_dir) / f"{source_id}__{slug}.html"
    if source_id == "lorcana_official_products":
        path_parts = [part for part in urlsplit(url).path.split("/") if part]
        try:
            product_index = path_parts.index("product")
        except ValueError:
            product_index = -1
        tail = path_parts[product_index + 1 :] if product_index >= 0 else []
        if len(tail) == 1:
            return Path(fixture_dir) / f"{source_id}__{tail[0]}.html"
        if len(tail) == 2 and tail[1] == "booster-pack":
            return Path(fixture_dir) / (
                f"{source_id}__{tail[0]}__booster_pack.html"
            )
    url_parts = urlsplit(url)
    if source_id == KONAMI_STYLE_SOURCE and url_parts.path.endswith("/detail.php"):
        product_id = next(
            (
                value.split("=", 1)[1]
                for value in url_parts.query.split("&")
                if value.startswith("product_id=") and "=" in value
            ),
            "detail",
        )
        return Path(fixture_dir) / f"{source_id}__{product_id}.html"
    if source_id == TAKARATOMY_MALL_SOURCE and "/shop/g/" in url_parts.path:
        product_id = url_parts.path.rstrip("/").rsplit("/", 1)[-1]
        return Path(fixture_dir) / f"{source_id}__{product_id}.html"
    if source_id == ONEPIECE_SHOP_SOURCE and "/news/" in url_parts.path:
        article_id = url_parts.path.rsplit("/", 1)[-1].removesuffix(".html")
        return Path(fixture_dir) / f"{source_id}__{article_id}.html"
    if source_id == PREMIUM_BANDAI_DB_SOURCE and "/item/" in url_parts.path:
        item_id = url_parts.path.rstrip("/").rsplit("/", 1)[-1]
        return Path(fixture_dir) / f"{source_id}__{item_id}.html"
    if is_furuichi_source(source_id) and not is_furuichi_news_index(source_id, url):
        article_id = url_parts.path.rstrip("/").rsplit("/", 1)[-1]
        return Path(fixture_dir) / f"{source_id}__{article_id}.html"
    return Path(fixture_dir) / f"{source_id}.html"


def _provider_host(url: str) -> str:
    host = urlsplit(url).netloc.casefold()
    for prefix in ("www.", "ww.", "w.", "mobile."):
        if host.startswith(prefix):
            return host.removeprefix(prefix)
    return host


_TRANSPORT_ALERT_REASONS = {
    "browser_fallback_failed",
    "host_circuit_open",
    "http_fetch_failed",
    "page_fetch_failed",
    "repeated_http_error",
}

_CAUSE_LABELS = {
    "ConnectError": "接続エラー",
    "ConnectTimeout": "接続タイムアウト",
    "ReadError": "読み込みエラー",
    "ReadTimeout": "読み込みタイムアウト",
    "RemoteProtocolError": "通信手順エラー",
    "challenge": "Cloudflare・CAPTCHA等の確認画面",
    "login": "ログイン画面",
}


def _cause_label(problem: FetchProblem) -> str:
    cause = problem.cause_code or ""
    if cause.startswith("http_status_"):
        return f"HTTP {cause.removeprefix('http_status_')}"
    return _CAUSE_LABELS.get(cause, cause or "原因不明の取得失敗")


def _healthy_fallbacks(
    config: Config,
    source_outcomes: dict[str, bool],
    degraded_source_ids: set[str] | None = None,
) -> dict[str, list[str]]:
    """Return failed or partially degraded sources covered elsewhere."""

    degraded_source_ids = degraded_source_ids or set()
    by_id = {source.id: source for source in config.sources}
    covered: dict[str, list[str]] = {}
    for source in config.sources:
        if (
            source_outcomes.get(source.id, True)
            and source.id not in degraded_source_ids
        ) or not source.fallback_source_ids:
            continue
        healthy = [
            fallback_id
            for fallback_id in source.fallback_source_ids
            if source_outcomes.get(fallback_id) is True
        ]
        if not healthy:
            continue
        verified_games = {
            game_id
            for game_id, status in source.supported_games.items()
            if status == GameSupport.VERIFIED
        }
        covered_games = {
            game_id
            for game_id in verified_games
            if any(
                by_id[fallback_id].supported_games.get(game_id)
                == GameSupport.VERIFIED
                for fallback_id in healthy
            )
        }
        if verified_games and verified_games <= covered_games:
            covered[source.id] = healthy
    return covered


def _monitor_outcome_counts(
    source_outcomes: dict[str, bool],
    covered_sources: dict[str, list[str]],
) -> tuple[int, int, int]:
    """Return mutually exclusive success, degraded, and failed counts."""

    covered_ids = set(covered_sources) & set(source_outcomes)
    successful = sum(
        outcome and source_id not in covered_ids
        for source_id, outcome in source_outcomes.items()
    )
    degraded = len(covered_ids)
    failed = sum(
        not outcome and source_id not in covered_ids
        for source_id, outcome in source_outcomes.items()
    )
    return successful, degraded, failed


def _suppress_covered_transport_alerts(
    alerts: list[Alert],
    config: Config,
    source_outcomes: dict[str, bool],
    covered_sources: dict[str, list[str]],
    source_failed_hosts: dict[str, set[str]] | None = None,
) -> list[Alert]:
    """Keep raw health in state, but notify only when coverage is unavailable."""

    if not covered_sources:
        return alerts
    kept: list[Alert] = []
    for alert in alerts:
        if alert.reason_code not in _TRANSPORT_ALERT_REASONS:
            kept.append(alert)
            continue
        if alert.source_id in covered_sources:
            continue
        if not alert.source_id.startswith("provider:"):
            kept.append(alert)
            continue

        host = alert.source_id.removeprefix("provider:")
        failed_sources = (
            [
                source.id
                for source in config.sources
                if source_outcomes.get(source.id) is False
                and any(provider_host(url) == host for url in source.discovery_urls)
            ]
            if source_failed_hosts is None
            else [
                source_id
                for source_id, failed_hosts in source_failed_hosts.items()
                if host in failed_hosts
            ]
        )
        if failed_sources and all(
            source_id in covered_sources for source_id in failed_sources
        ):
            continue
        kept.append(alert)
    return kept


def _collapse_provider_http_alerts(alerts: list[Alert]) -> list[Alert]:
    """Report one provider outage instead of one Discord alert per monitored account."""
    grouped: dict[tuple[str, str], list[Alert]] = {}
    passthrough: list[Alert] = []
    circuit_hosts = {
        _provider_host(alert.target_url)
        for alert in alerts
        if alert.reason_code == "host_circuit_open"
    }
    for alert in alerts:
        if alert.reason_code not in _TRANSPORT_ALERT_REASONS - {
            "host_circuit_open"
        }:
            passthrough.append(alert)
            continue
        host = _provider_host(alert.target_url)
        if host in circuit_hosts:
            continue
        grouped.setdefault((host, alert.reason_code), []).append(alert)
    for (host, reason), items in grouped.items():
        if len(items) == 1:
            passthrough.extend(items)
            continue
        statuses = {item.http_status for item in items}
        passthrough.append(
            Alert(
                None,
                f"provider:{host}",
                f"https://{host}/",
                f"取得元 {host}",
                [],
                reason,
                "同一取得元で複数監視先のHTTP取得に失敗しています",
                next(iter(statuses)) if len(statuses) == 1 else None,
                f"https://{host}/",
            ).with_fingerprint()
        )
    return passthrough


def _problem_alert(source: SourceConfig, problem: FetchProblem) -> Alert:
    if problem.reason.startswith("http_fetch_failed"):
        reason_code = "http_fetch_failed"
        summary = f"HTTP取得に失敗: {_cause_label(problem)}"
        if problem.attempts:
            summary += f"（{problem.attempts}回試行）"
    elif problem.reason.startswith("http_status_"):
        reason_code = "repeated_http_error"
        summary = f"HTTPエラー: {problem.status_code}"
    elif problem.reason.startswith("browser_fetch_failed"):
        reason_code = "browser_fallback_failed"
        summary = f"JavaScript表示の取得に失敗: {problem.reason}"
    else:
        reason_code = "page_fetch_failed"
        summary = f"取得ページを監視可能な本文として確認できません: {problem.reason}"
    return _alert(
        source.id,
        source.name,
        problem.url,
        reason_code,
        summary,
        problem.status_code,
    )


def _host_circuit_alert(problem: FetchProblem) -> Alert:
    host = provider_host(problem.url)
    label = _cause_label(problem)
    if problem.attempts:
        summary = (
            f"取得失敗が連続{problem.attempts}回発生しました"
            f"（直近の原因: {label}）。この実行中の残りアクセスを中止しました"
        )
    else:
        summary = (
            f"取得失敗が連続しました（直近の原因: {label}）。"
            "この実行中の残りアクセスを中止しました"
        )
    return Alert(
        None,
        f"provider:{host}",
        f"https://{host}/",
        f"取得元 {host}",
        [],
        "host_circuit_open",
        summary,
        problem.status_code,
        f"https://{host}/",
    ).with_fingerprint()


def _state_mapping(state: MonitorState | None, key: str) -> dict[str, object]:
    if state is None:
        return {}
    value = state.data.setdefault(key, {})
    if isinstance(value, dict):
        return value
    replacement: dict[str, object] = {}
    state.data[key] = replacement
    return replacement


def _current_ocr_pending_urls(
    pending: dict[str, object],
    source_id: str,
    attempt_token: str,
) -> set[str]:
    """Return OCR candidates that failed during this exact pipeline run."""

    urls: set[str] = set()
    for status_url, raw in pending.items():
        if not isinstance(raw, dict):
            continue
        if (
            raw.get("source_id") == source_id
            and raw.get("last_attempt_token") == attempt_token
        ):
            urls.add(status_url)
    return urls


def run_pipeline(
    config: Config,
    fixture_dir: str | None = None,
    source_filter: set[str] | None = None,
    ocr_cache: dict[str, str] | None = None,
    monitor_state: MonitorState | None = None,
    http_fetcher: HttpFetcher | None = None,
    browser_fetcher: BrowserFetcher = fetch_rendered_html,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    pipeline_started = time.perf_counter()
    cases: list[LotteryCase] = []
    releases: list[Release] = []
    alerts: list[Alert] = []
    fetcher = http_fetcher or HttpFetcher(
        timeout=float(config.system.get("request_timeout_seconds", 20)),
        max_retries=int(config.system.get("max_retries", 2)),
        request_budget_seconds=float(
            config.system.get("request_budget_seconds", 60)
        ),
        retry_backoff_seconds=tuple(
            float(value)
            for value in config.system.get("retry_backoff_seconds", [0, 0])
        ),
        minimum_host_interval=float(
            config.system.get("minimum_host_interval_seconds", 5)
        ),
    )
    page_fetcher = PageFetcher(
        fetcher,
        browser_fetcher,
        circuit_breaker=HostCircuitBreaker(
            threshold=max(
                2,
                int(config.system.get("consecutive_http_error_threshold", 2)),
            )
        ),
        timeout_ms=int(float(config.system.get("request_timeout_seconds", 20)) * 1_000),
        conditional_get=bool(config.system.get("conditional_get", True)),
    )
    http_cache = _state_mapping(monitor_state, "http_cache")
    ocr_pending = _state_mapping(monitor_state, "ocr_pending")
    ocr_cache_meta = _state_mapping(monitor_state, "ocr_cache_meta")
    opened_hosts_reported: set[str] = set()
    source_outcomes: dict[str, bool] = {}
    source_failed_hosts: dict[str, set[str]] = {}
    run_token = datetime.now(UTC).isoformat()
    selected_sources = [
        source
        for source in config.sources
        if source.enabled
        and any(
            source.supports(game_id)
            for game_id in config.active_game_ids
        )
        and (source_filter is None or source.id in source_filter)
    ]

    def fetch_page(source: SourceConfig, url: str) -> PageResult:
        browser_url = (
            pokemon_release_window_url(
                url,
                int(config.system.get("max_future_days", 365)),
            )
            if source.id == "pokemon_official_products"
            else None
        )
        return page_fetcher.fetch(
            url,
            source,
            http_cache,
            browser_url=browser_url,
        )

    root_prefetcher = _RootPrefetcher(
        selected_sources,
        1
        if fixture_dir
        else int(config.system.get("max_parallel_hosts", 6)),
        fetch_page,
    )

    for source in selected_sources:
        started = time.perf_counter()
        metrics = SourceMetrics(source.id)
        uses_parallel_discovery_paths = source.id in {
            "snkrdunk_pokemon",
            "snkrdunk_onepiece",
            "nyuka_now_fullcomp_livepocket",
        }
        configured_root_urls = list(source.discovery_urls)
        repair_urls: list[str] = []
        primary_roots: list[str] = []
        is_yahoo_source = is_yahoo_realtime_source(source)
        always_fetch_roots = list(tsutaya_line_form_urls(source))
        if monitor_state is not None and is_yahoo_source:
            repair_urls = yahoo_repair_discovery_urls(
                source,
                monitor_state.data.get("seen_cases"),
            )

        # Yahoo検索は同一ホストの検索語違いをすべて通常経路として扱う。
        # Twstalkerなど別ホストのURLは、Yahooの取得・解析に失敗した時だけ
        # 順番に使う。仮商品名の自己修復URLは予備経路ではないため常に残す。
        if is_yahoo_source and configured_root_urls:
            primary_host = provider_host(configured_root_urls[0])
            primary_roots = [
                url
                for url in configured_root_urls
                if provider_host(url) == primary_host
            ]
            remaining_roots = [
                url
                for url in configured_root_urls
                if provider_host(url) != primary_host
                and url not in always_fetch_roots
            ]
            discovery_urls = [
                (url, True)
                for url in [*primary_roots, *repair_urls, *always_fetch_roots]
                if url not in remaining_roots
            ]
        else:
            remaining_roots = (
                [] if uses_parallel_discovery_paths else configured_root_urls[1:]
            )
            discovery_urls = (
                [(url, True) for url in configured_root_urls]
                if uses_parallel_discovery_paths
                else [(configured_root_urls[0], True)]
                if configured_root_urls
                else []
            )
        remaining_configured_roots = set(remaining_roots)

        # 設定済みのroot URLだけが次の予備URLを起動できる。自己修復URLの
        # 一時失敗でTwstalkerへ切り替わると、Yahoo正常時省略の意味がなくなる。
        fallback_trigger_urls = (
            set(configured_root_urls) - set(always_fetch_roots)
            if not uses_parallel_discovery_paths
            else set()
        )
        required_supplemental_urls = set(always_fetch_roots)
        supplemental_urls = set(repair_urls) | required_supplemental_urls
        visited_urls: set[str] = set()
        completed_page = False
        last_failure_alert: Alert | None = None
        yahoo_primary_parsed_item = False

        def enqueue_fallback_root(
            queued_urls: list[tuple[str, bool]] = discovery_urls,
            fallback_roots: list[str] = remaining_roots,
        ) -> None:
            if fallback_roots:
                queued_urls.append((fallback_roots.pop(0), True))

        def enqueue_fallback_after_root_failure(
            failed_url: str,
            fallback_triggers: set[str] = fallback_trigger_urls,
            yahoo_source: bool = is_yahoo_source,
            yahoo_roots: list[str] = primary_roots,
            queued_urls: list[tuple[str, bool]] = discovery_urls,
        ) -> None:
            if failed_url not in fallback_triggers:
                return
            if yahoo_source and failed_url in yahoo_roots and any(
                queued_url in yahoo_roots for queued_url, _ in queued_urls
            ):
                # Try every configured Yahoo query before consuming one of the
                # cross-host fallbacks.  A failure on the first query must not
                # pre-queue every fallback even if the second query also fails.
                return
            enqueue_fallback_root()

        if not discovery_urls:
            alerts.append(
                _alert(
                    source.id,
                    source.name,
                    "",
                    "discovery_urls_missing",
                    "有効な監視元にdiscovery_urlsが設定されていません",
                )
            )
            metrics.last_error = "discovery_urls_missing"

        while discovery_urls:
            url, is_root = discovery_urls.pop(0)
            if url in visited_urls:
                continue
            visited_urls.add(url)
            try:
                if fixture_dir:
                    fixture = _fixture_path(fixture_dir, source.id, url)
                    result = PageResult(
                        url,
                        fixture.read_text(encoding="utf-8") if fixture.exists() else "",
                        200,
                        "fixture",
                    )
                else:
                    prefetched = (
                        root_prefetcher.take(source, url)
                        if is_root
                        and source.discovery_urls
                        and url == source.discovery_urls[0]
                        else None
                    )
                    result = prefetched or fetch_page(source, url)
                metrics.fetched(result)
            except (CircuitOpenError, FetchProblem) as problem:
                metrics.failed(problem)
                source_failed_hosts.setdefault(source.id, set()).add(
                    provider_host(problem.url)
                )
                if problem.reason == "host_circuit_open":
                    host = provider_host(problem.url)
                    if host not in opened_hosts_reported:
                        opened_hosts_reported.add(host)
                        alerts.append(
                            _host_circuit_alert(problem)
                        )
                elif url in required_supplemental_urls:
                    alerts.append(_problem_alert(source, problem))
                else:
                    last_failure_alert = _problem_alert(source, problem)
                if is_root and url not in required_supplemental_urls:
                    enqueue_fallback_after_root_failure(url)
                continue
            except Exception as exc:
                unexpected_problem = FetchProblem(
                    url,
                    f"fetch_exception:{type(exc).__name__}",
                    fetch_method="unknown",
                )
                metrics.failed(unexpected_problem)
                unexpected_alert = _alert(
                    source.id,
                    source.name,
                    url,
                    "fetch_exception",
                    f"取得処理の想定外例外: {type(exc).__name__}: {str(exc)[:180]}",
                )
                if url in required_supplemental_urls:
                    alerts.append(unexpected_alert)
                else:
                    last_failure_alert = unexpected_alert
                if is_root and url not in required_supplemental_urls:
                    enqueue_fallback_after_root_failure(url)
                continue

            if result.not_modified:
                if url not in supplemental_urls:
                    completed_page = True
                continue
            html = result.html

            try:
                if is_official_retailer_index(source.id, url):
                    discovered = discover_official_retailer_urls(
                        html,
                        url,
                        source,
                        config,
                    )
                    discovery_urls.extend(
                        (item, False)
                        for item in discovered
                        if item not in visited_urls
                    )
                    if not discovered and official_retailer_index_should_have_links(
                        source.id,
                        html,
                    ):
                        alerts.append(
                            _alert(
                                source.id,
                                source.name,
                                url,
                                "official_retailer_links_missing",
                                "公式販売元の一覧から対象BOXの個別ページを発見できません",
                            )
                        )
                        metrics.last_error = "official_retailer_links_missing"
                    else:
                        completed_page = True
                    metrics.excluded_count += 1
                    # List pages contain release dates, campaign dates and old
                    # entries together.  Only the scoped detail parser may emit an
                    # application or sale event.
                    continue

                if is_furuichi_news_index(source.id, url):
                    discovered = discover_furuichi_lottery_urls(
                        html,
                        url,
                        source,
                        config,
                    )
                    discovery_urls.extend(
                        (item, False)
                        for item in discovered
                        if item not in visited_urls
                    )
                    if discovered:
                        completed_page = True
                    elif furuichi_index_has_target_lottery(html, source, config):
                        alerts.append(
                            _alert(
                                source.id,
                                source.name,
                                url,
                                "furuichi_lottery_detail_link_missing",
                                (
                                    "ふるいち公式一覧に対象BOX抽選があるが"
                                    "個別記事URLを発見できません"
                                ),
                            )
                        )
                        metrics.last_error = "furuichi_lottery_detail_link_missing"
                    else:
                        completed_page = True
                    metrics.excluded_count += 1
                    continue

                if is_lorcana_product_index(source.id, url):
                    discovered = discover_lorcana_product_urls(html, url)
                    discovery_urls.extend(
                        (item, False)
                        for item in discovered
                        if item not in visited_urls
                    )
                    if not discovered:
                        alerts.append(
                            _alert(
                                source.id,
                                source.name,
                                url,
                                "discovery_links_missing",
                                "ロルカナ公式商品一覧からブースター商品ページを発見できません",
                            )
                        )
                        metrics.last_error = "discovery_links_missing"
                    else:
                        completed_page = True
                    metrics.excluded_count += 1
                    continue

                if is_geo_news_index(source.id, url):
                    discovered = discover_geo_news_urls(html, url, source, config)
                    if discovered:
                        discovery_urls.extend(
                            (item, False)
                            for item in discovered
                            if item not in visited_urls
                        )
                    else:
                        completed_page = True
                        metrics.excluded_count += 1
                    # The index exposes publication/release dates but not the
                    # application period. Parse only full articles.
                    continue

                if is_retailer_lottery_index(source, url):
                    index_error = retailer_lottery_index_error(html, source)
                    if index_error:
                        alerts.append(
                            _alert(
                                source.id,
                                source.name,
                                url,
                                "retailer_index_unavailable",
                                index_error,
                            )
                        )
                        metrics.last_error = "retailer_index_unavailable"
                        continue
                    discovered = discover_retailer_lottery_urls(
                        html, url, source, config
                    )
                    discovery_urls.extend(
                        (item, False)
                        for item in discovered
                        if item not in visited_urls
                    )
                    index_text = BeautifulSoup(html, "lxml").get_text(
                        " ", strip=True
                    )
                    has_target_game = any(
                        word in index_text
                        for word in (
                            "ポケモンカード",
                            "ポケカ",
                            "ONE PIECEカード",
                            "ワンピースカード",
                            "ワンピカード",
                            "フュージョンワールド",
                            "DBFW",
                            "遊戯王OCG",
                            "遊戯王",
                            "ディズニー・ロルカナ",
                            "ロルカナ",
                        )
                    )
                    has_box_lottery = "抽選" in index_text and (
                        "BOX" in index_text.upper()
                        or any(
                            word in index_text
                            for word in (
                                "拡張パック",
                                "ハイクラスパック",
                                "ブースターパック",
                                "MANGA BOOSTER",
                                "STORY BOOSTER",
                                "基本パック",
                                "スペシャルパック",
                                "LIMITED PACK",
                            )
                        )
                    )
                    if not discovered and has_target_game and has_box_lottery:
                        alerts.append(
                            _alert(
                                source.id,
                                source.name,
                                url,
                                "retailer_lottery_detail_link_missing",
                                "公式一覧に対象BOX抽選があるが個別ページURLを発見できません",
                            )
                        )
                    if not discovered:
                        completed_page = True
                        metrics.excluded_count += 1
                    continue

                if is_dragonball_official_store_index(source.id, url):
                    discovered = discover_dragonball_official_store_urls(html, url)
                    discovery_urls.extend(
                        (item, False)
                        for item in discovered
                        if item not in visited_urls
                    )
                    index_text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
                    if (
                        not discovered
                        and "ブースターパック" in index_text
                        and "抽選" in index_text
                    ):
                        alerts.append(
                            _alert(
                                source.id,
                                source.name,
                                url,
                                "discovery_links_missing",
                                "公式ストア一覧からBOX抽選販売の詳細記事を発見できません",
                            )
                        )
                    if not discovered:
                        completed_page = True
                        metrics.excluded_count += 1
                    continue

                if is_livepocket_source(source) and is_livepocket_search_page(url):
                    discovered = discover_livepocket_event_urls(
                        html, url, source, config
                    )
                    discovery_urls.extend(
                        (item, False)
                        for item in discovered
                        if item not in visited_urls
                    )
                    index_text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
                    has_target_game = any(
                        word in index_text
                        for word in (
                            "ポケモンカード",
                            "ポケカ",
                            "ONE PIECEカード",
                            "ワンピースカード",
                            "ワンピカード",
                            "ドラゴンボールスーパーカードゲーム",
                            "フュージョンワールド",
                            "DBFW",
                            "遊戯王OCG",
                            "遊戯王",
                            "ディズニー・ロルカナ",
                            "ロルカナ",
                        )
                    )
                    has_box_lottery = "抽選" in index_text and (
                        "購入権" in index_text
                        or "BOX" in index_text.upper()
                        or any(
                            word in index_text
                            for word in (
                                "拡張パック",
                                "ハイクラスパック",
                                "ブースターパック",
                            )
                        )
                    )
                    if not discovered and has_target_game and has_box_lottery:
                        alerts.append(
                            _alert(
                                source.id,
                                source.name,
                                url,
                                "livepocket_relevant_event_link_missing",
                                "検索結果に対象BOX抽選があるが個別ページURLを発見できません",
                            )
                        )
                    if not discovered:
                        completed_page = True
                        metrics.excluded_count += 1
                    continue

                if is_pokemon_center_news_index(source.id, url):
                    discovered = discover_pokemon_center_news_urls(
                        html, url, source
                    )
                    discovery_urls.extend(
                        (item, False)
                        for item in discovered
                        if item not in visited_urls
                    )
                    index_text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
                    if (
                        not discovered
                        and "抽選" in index_text
                        and any(
                            word in index_text
                            for word in ("ポケモンカード", "カードゲーム")
                        )
                    ):
                        alerts.append(
                            _alert(
                                source.id,
                                source.name,
                                url,
                                "discovery_links_missing",
                                "公式お知らせ一覧からポケモンカード抽選記事を発見できません",
                            )
                        )
                    if not discovered:
                        completed_page = True
                        metrics.excluded_count += 1
                    continue

                if source.id in {
                    "snkrdunk_pokemon",
                    "snkrdunk_onepiece",
                } and is_snkrdunk_schedule_page(html):
                    discovered = discover_snkrdunk_article_urls(
                        html, url, source
                    )
                    discovery_urls.extend(
                        (item, False)
                        for item in discovered
                        if item not in visited_urls
                    )
                    if not discovered:
                        alerts.append(
                            _alert(
                                source.id,
                                source.name,
                                url,
                                "discovery_links_missing",
                                "発売スケジュールから新弾の予約・抽選記事を発見できません",
                            )
                        )
                        completed_page = True
                        metrics.excluded_count += 1
                    continue

                parser = _parser_for(source)
                primary_without_candidates_requires_fallback = False
                if is_tsutaya_line_form_url(source, url):
                    parsed_cases, parsed_releases, parsed_alerts = (
                        parse_tsutaya_line_form(html, url, source, config)
                    )
                elif is_yahoo_realtime_source(source):
                    if (
                        url in primary_roots
                        and not yahoo_realtime_page_loaded(html, source)
                    ):
                        raise ValueError(
                            "Yahoo result contains neither the configured account "
                            "nor an explicit empty-result marker"
                        )
                    parsed_cases, parsed_releases, parsed_alerts = (
                        parse_yahoo_realtime(
                            html,
                            url,
                            source,
                            config,
                            ocr_reader=read_image_text if not fixture_dir else None,
                            ocr_cache=ocr_cache,
                            known_releases=releases,
                            ocr_pending=ocr_pending,
                            ocr_cache_meta=ocr_cache_meta,
                            ocr_attempt_token=run_token,
                        )
                    )
                    if url in primary_roots and (
                        parsed_cases or parsed_releases
                    ):
                        yahoo_primary_parsed_item = True
                    has_queued_primary = any(
                        queued_url in primary_roots
                        for queued_url, _ in discovery_urls
                    )
                    primary_without_candidates_requires_fallback = (
                        source.fallback_on_empty_result
                        and is_root
                        and url in primary_roots
                        and not has_queued_primary
                        and not yahoo_primary_parsed_item
                    )
                    if primary_without_candidates_requires_fallback:
                        enqueue_fallback_root()
                    elif (
                        source.fallback_on_empty_result
                        and is_root
                        and url in remaining_configured_roots
                        and not parsed_cases
                        and not parsed_releases
                        and remaining_roots
                    ):
                        # Fallbacks are ordered, not mutually exclusive.  If an
                        # official direct-post endpoint is temporarily empty or
                        # no longer parseable, continue to the profile mirror
                        # instead of declaring the source healthy at zero items.
                        enqueue_fallback_root()
                        primary_without_candidates_requires_fallback = True
                    # Yahoo can load normally while its temporary image proxy
                    # has already expired.  This is a content failure, so use
                    # Twstalker only then instead of loading it on every
                    # otherwise healthy Yahoo run.
                    if (
                        is_root
                        and url in primary_roots
                        and _current_ocr_pending_urls(
                            ocr_pending,
                            source.id,
                            run_token,
                        )
                    ):
                        enqueue_fallback_root()
                elif is_furuichi_source(source.id):
                    parsed_cases, parsed_releases, parsed_alerts = (
                        parse_furuichi_lottery_detail(
                            html,
                            url,
                            source,
                            config,
                            ocr_reader=read_image_text if not fixture_dir else None,
                            ocr_cache=ocr_cache,
                            ocr_cache_meta=ocr_cache_meta,
                        )
                    )
                else:
                    parsed_cases, parsed_releases, parsed_alerts = parser(
                        html, url, source, config
                    )
                original_item_count = len(parsed_cases) + len(parsed_releases)
                parsed_cases = [
                    case
                    for case in parsed_cases
                    if source.supports(case.game_id)
                    and case.game_id in config.active_game_ids
                ]
                parsed_releases = [
                    release
                    for release in parsed_releases
                    if source.supports(release.game_id)
                    and release.game_id in config.active_game_ids
                ]
                parsed_alerts = [
                    alert
                    for alert in parsed_alerts
                    if alert.game_id is None
                    or (
                        source.supports(alert.game_id)
                        and alert.game_id in config.active_game_ids
                    )
                ]
                filtered_item_count = original_item_count - (
                    len(parsed_cases) + len(parsed_releases)
                )
                cases.extend(parsed_cases)
                releases.extend(parsed_releases)
                alerts.extend(parsed_alerts)
                parsed_total = len(parsed_cases) + len(parsed_releases)
                metrics.parsed_count += parsed_total
                metrics.excluded_count += filtered_item_count
                if parsed_total == 0 and filtered_item_count == 0:
                    metrics.excluded_count += 1
                if (
                    url not in supplemental_urls
                    and not primary_without_candidates_requires_fallback
                ):
                    completed_page = True
            except Exception as exc:
                metrics.last_error = f"parser_exception:{type(exc).__name__}"
                failure_alert = _alert(
                    source.id,
                    source.name,
                    url,
                    "parser_exception",
                    f"Parser例外: {type(exc).__name__}: {str(exc)[:180]}",
                    result.status_code,
                )
                if url in required_supplemental_urls:
                    alerts.append(failure_alert)
                elif is_root:
                    last_failure_alert = failure_alert
                    enqueue_fallback_after_root_failure(url)
                else:
                    alerts.append(failure_alert)
                continue

        if is_yahoo_source:
            still_pending = {
                status_url
                for status_url, raw in ocr_pending.items()
                if isinstance(raw, dict) and raw.get("source_id") == source.id
            }
            alerts[:] = [
                alert
                for alert in alerts
                if not (
                    alert.source_id == source.id
                    and alert.reason_code == "yahoo_image_ocr_repeated_failure"
                    and alert.target_url not in still_pending
                )
            ]
        if not completed_page and last_failure_alert:
            alerts.append(last_failure_alert)
        source_outcomes[source.id] = completed_page
        metrics.duration_ms = max(
            round((time.perf_counter() - started) * 1_000),
            metrics.fetch_duration_ms,
        )
        if monitor_state is not None:
            try:
                monitor_state.record_monitor(
                    source.id,
                    metrics.as_state(),
                    success=completed_page,
                )
            except Exception as exc:
                alerts.append(
                    _alert(
                        source.id,
                        source.name,
                        str(monitor_state.path),
                        "state_persist_failed",
                        f"monitor_state保存に失敗: {type(exc).__name__}: {str(exc)[:180]}",
                    )
                )
        root_prefetcher.source_done(source)

    root_prefetcher.close()

    try:
        cases, lottery_merge_alerts = merge_lotteries(cases)
    except Exception as exc:
        lottery_merge_alerts = [
            _alert(
                "pipeline",
                "抽選候補の統合",
                "",
                "lottery_merge_exception",
                f"抽選候補の統合に失敗: {type(exc).__name__}: {str(exc)[:180]}",
            )
        ]
    try:
        releases, release_merge_alerts = merge_releases(releases)
    except Exception as exc:
        release_merge_alerts = [
            _alert(
                "pipeline",
                "発売候補の統合",
                "",
                "release_merge_exception",
                f"発売候補の統合に失敗: {type(exc).__name__}: {str(exc)[:180]}",
            )
        ]
    covered_sources = _healthy_fallbacks(
        config,
        source_outcomes,
        set(source_failed_hosts),
    )
    visible_alerts = _suppress_covered_transport_alerts(
        alerts + lottery_merge_alerts + release_merge_alerts,
        config,
        source_outcomes,
        covered_sources,
        source_failed_hosts,
    )
    final_alerts = _collapse_provider_http_alerts(visible_alerts)
    successful_monitors, degraded_monitors, failed_monitors = (
        _monitor_outcome_counts(source_outcomes, covered_sources)
    )
    if monitor_state is not None:
        with suppress(Exception):
            monitor_state.record_monitor_coverage(covered_sources)
        with suppress(Exception):
            monitor_state.record_run_summary(
                {
                    "successful_monitors": successful_monitors,
                    "degraded_monitors": degraded_monitors,
                    "failed_monitors": failed_monitors,
                    "source_failures": sum(
                        not outcome for outcome in source_outcomes.values()
                    ),
                    "alerts": len(final_alerts),
                    "new_lotteries": 0,
                    "new_releases": 0,
                    "duration_ms": round(
                        (time.perf_counter() - pipeline_started) * 1_000
                    ),
                }
            )
    return cases, releases, final_alerts


def load_and_run(
    path: str = "sites.yaml",
    fixture_dir: str | None = None,
    source_filter: set[str] | None = None,
) -> tuple[list[LotteryCase], list[Release], list[Alert]]:
    return run_pipeline(load_config(path), fixture_dir, source_filter)
