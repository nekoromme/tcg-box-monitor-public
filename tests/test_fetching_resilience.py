from __future__ import annotations

import threading
import time
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
import yaml
from freezegun import freeze_time

import tcg_monitor.pipeline as pipeline
from tcg_monitor.config import ConfigError, load_config
from tcg_monitor.fetching import FetchProblem, PageFetcher, PageKind, classify_page
from tcg_monitor.http_client import FetchResult, HttpAttemptsExhausted, HttpFetcher
from tcg_monitor.japanese_datetime import parse_first_datetime
from tcg_monitor.models import (
    GameSupport,
    Release,
    RenderMode,
    SourceConfig,
    SourceTier,
)
from tcg_monitor.parsers.generic import parse_generic
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.state import MonitorState


class FakeHttpFetcher:
    def __init__(self, responses: dict[str, FetchResult | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str | None, str | None]] = []

    def fetch(
        self,
        url: str,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        self.calls.append((url, etag, last_modified))
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response


def _source(
    source_id: str,
    urls: list[str],
    render_mode: RenderMode = RenderMode.HTTP,
    supported_games: dict[str, GameSupport] | None = None,
) -> SourceConfig:
    return SourceConfig(
        source_id,
        source_id,
        SourceTier.OFFICIAL,
        supported_games or {"pokemon_card": GameSupport.VERIFIED},
        ["lottery_discovery"],
        True,
        urls,
        render_mode=render_mode,
    )


def _config(*sources: SourceConfig):
    base = load_config("sites.yaml")
    return replace(
        base,
        system={
            **base.system,
            "minimum_host_interval_seconds": 0,
            "request_timeout_seconds": 1,
        },
        sources=list(sources),
    )


def _response(url: str, status: int, text: str, **headers: str) -> FetchResult:
    return FetchResult(url, status, text, headers)


def test_parser_exception_does_not_stop_other_monitors(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failed_url = "https://broken.example/lottery"
    healthy_url = "https://healthy.example/releases"
    failed_source = _source("broken_parser", [failed_url])
    healthy_source = _source("healthy_parser", [healthy_url])
    fetcher = FakeHttpFetcher(
        {
            failed_url: _response(failed_url, 200, "<main>抽選ページの本文</main>"),
            healthy_url: _response(healthy_url, 200, "<main>発売ページの本文</main>"),
        }
    )
    release = Release(
        "pokemon_card",
        "拡張パック「テスト」",
        "拡張パック",
        "pokemon_card:test",
        date(2027, 1, 1),
        None,
        healthy_url,
        healthy_url,
        SourceTier.OFFICIAL,
        "test",
        "high",
    ).with_id()

    def broken_parser(*_args: Any) -> tuple[list[Any], list[Any], list[Any]]:
        raise ValueError("unexpected structure")

    def healthy_parser(*_args: Any) -> tuple[list[Any], list[Release], list[Any]]:
        return [], [release], []

    monkeypatch.setattr(
        pipeline,
        "_parser_for",
        lambda source: broken_parser if source.id == "broken_parser" else healthy_parser,
    )
    state = MonitorState.load(tmp_path / "monitor_state.json")

    cases, releases, alerts = pipeline.run_pipeline(
        _config(failed_source, healthy_source),
        monitor_state=state,
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert not cases
    assert releases == [release]
    assert [alert.reason_code for alert in alerts] == ["parser_exception"]
    assert state.data["monitors"]["broken_parser"]["outcome"] == "failed"
    assert state.data["monitors"]["healthy_parser"]["outcome"] == "success"
    assert state.data["monitors"]["healthy_parser"]["parsed_count"] == 1
    assert state.data["last_run_summary"]["duration_ms"] >= 0


@pytest.mark.parametrize(
    ("mode", "http_text", "method", "http_calls", "browser_calls"),
    [
        (
            RenderMode.HTTP,
            "<main>通常のHTTP本文をそのまま解析します</main>",
            "http",
            1,
            0,
        ),
        (
            RenderMode.HTTP_NO_CHALLENGE_BYPASS,
            "<main>HTTP限定で取得する通常本文です</main>",
            "http",
            1,
            0,
        ),
        (RenderMode.PLAYWRIGHT, "", "playwright", 0, 1),
        (
            RenderMode.HTTP_THEN_PLAYWRIGHT_IF_EMPTY,
            "<html><div id='root'></div><script>boot()</script></html>",
            "playwright",
            1,
            1,
        ),
        (
            RenderMode.HTTP_THEN_BROWSER_IF_SHELL,
            "<html><p>JavaScript is required</p></html>",
            "playwright",
            1,
            1,
        ),
        (
            RenderMode.HTTP_THEN_BROWSER_ONCE_NO_CHALLENGE_BYPASS,
            "<html><div id='app'></div><script>boot()</script></html>",
            "playwright",
            1,
            1,
        ),
    ],
)
def test_render_mode_common_branches(
    mode: RenderMode,
    http_text: str,
    method: str,
    http_calls: int,
    browser_calls: int,
) -> None:
    url = "https://render.example/page"
    http = FakeHttpFetcher({url: _response(url, 200, http_text)})
    rendered_calls: list[str] = []

    def render(render_url: str, _selector: str | None, _timeout: int) -> str:
        rendered_calls.append(render_url)
        return "<main>Playwrightで取得した十分な本文です</main>"

    result = PageFetcher(http, render).fetch(url, _source("render", [url], mode), {})

    assert result.fetch_method == method
    assert len(http.calls) == http_calls
    assert len(rendered_calls) == browser_calls


def test_challenge_is_not_sent_to_browser() -> None:
    url = "https://challenge.example/page"
    http = FakeHttpFetcher(
        {
            url: _response(
                url,
                200,
                "<html><title>Attention Required</title><p>Cloudflare Ray ID</p></html>",
            )
        }
    )
    rendered_calls: list[str] = []

    def render(render_url: str, _selector: str | None, _timeout: int) -> str:
        rendered_calls.append(render_url)
        return "<main>should not be used</main>"

    with pytest.raises(FetchProblem, match="challenge"):
        PageFetcher(http, render).fetch(
            url,
            _source("challenge", [url], RenderMode.HTTP_THEN_BROWSER_IF_SHELL),
            {},
        )

    assert not rendered_calls


def test_cloudflare_waiting_room_is_classified_as_challenge() -> None:
    html = """
    <html><body>
      <h1>順番待ちに追加されました。</h1>
      <p>大量のトラフィックが発生しています。仮想キューを使用しています。</p>
      <footer>Waiting Room powered by Cloudflare</footer>
    </body></html>
    """

    assert classify_page(html) == PageKind.CHALLENGE


def test_explicit_browser_fallback_recovers_an_http_read_timeout() -> None:
    url = "https://slow-store.example/page"
    read_timeout = httpx.ReadTimeout(
        "response body timed out",
        request=httpx.Request("GET", url),
    )
    http = FakeHttpFetcher({url: HttpAttemptsExhausted(url, 3, read_timeout)})
    rendered_calls: list[str] = []

    def render(render_url: str, _selector: str | None, _timeout: int) -> str:
        rendered_calls.append(render_url)
        return "<main>ブラウザーでは正常に取得できた公開商品一覧です</main>"

    result = PageFetcher(http, render).fetch(
        url,
        _source(
            "slow-store",
            [url],
            RenderMode.HTTP_THEN_BROWSER_ONCE_NO_CHALLENGE_BYPASS,
        ),
        {},
    )

    assert result.fetch_method == "playwright"
    assert rendered_calls == [url]


def test_http_403_is_never_sent_to_browser_fallback() -> None:
    url = "https://blocked-store.example/page"
    http = FakeHttpFetcher({url: _response(url, 403, "<main>forbidden</main>")})
    rendered_calls: list[str] = []

    with pytest.raises(FetchProblem, match="http_status_403"):
        PageFetcher(
            http,
            lambda render_url, *_args: rendered_calls.append(render_url) or "",
        ).fetch(
            url,
            _source(
                "blocked-store",
                [url],
                RenderMode.HTTP_THEN_BROWSER_ONCE_NO_CHALLENGE_BYPASS,
            ),
            {},
        )

    assert not rendered_calls


def test_storefront_with_header_login_form_is_normal_content() -> None:
    product_rows = "".join(f"<li>商品{i} 在庫あり 詳細を見る</li>" for i in range(250))
    html = f"""
    <html>
      <head><title>エディオン公式通販</title></head>
      <body>
        <header>
          <form hidden>
            <h2>会員ログイン</h2>
            <input type="password" name="password">
          </form>
        </header>
        <main>
          <h1>家電・おもちゃ・ホビーの商品一覧</h1>
          <ul>{product_rows}</ul>
        </main>
      </body>
    </html>
    """

    assert classify_page(html) == PageKind.CONTENT


@pytest.mark.parametrize(
    "html",
    [
        """
        <html><head><title>ログイン</title></head>
        <body><h1>ログイン</h1><form><input type="password"></form></body></html>
        """,
        """
        <html><body><p>このページを見るにはログインしてください</p></body></html>
        """,
    ],
)
def test_actual_login_gate_is_still_detected(html: str) -> None:
    assert classify_page(html) == PageKind.LOGIN


def test_livepocket_robot_verification_is_a_challenge() -> None:
    url = "https://livepocket.jp/event/search?word=test"
    http = FakeHttpFetcher(
        {
            url: _response(
                url,
                202,
                (
                    "<html><h1>JavaScript is disabled</h1>"
                    "<p>In order to continue, we need to verify that you're not a robot.</p>"
                    "</html>"
                ),
            )
        }
    )

    with pytest.raises(FetchProblem, match="challenge"):
        PageFetcher(http, lambda *_args: "").fetch(
            url,
            _source(
                "livepocket",
                [url],
                RenderMode.HTTP_THEN_BROWSER_ONCE_NO_CHALLENGE_BYPASS,
            ),
            {},
        )


def test_http_fetcher_sends_identified_browser_accept_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status_code = 200
        text = "<main>正常な本文です</main>"
        headers: dict[str, str] = {}

    class RecordingClient:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

        def get(self, _url: str, *, headers: dict[str, str], timeout: float) -> Response:
            assert timeout == 1
            self.headers = headers
            return Response()

    monkeypatch.setenv("MONITOR_USER_AGENT_CONTACT", "monitor@example.test")
    client = RecordingClient()
    fetcher = HttpFetcher(
        timeout=1,
        max_retries=0,
        minimum_host_interval=0,
        client=client,
    )

    fetcher.fetch("https://headers.example/page", etag='"v1"')

    assert client.headers["User-Agent"].endswith("(+monitor@example.test)")
    assert client.headers["Accept"].startswith("text/html")
    assert client.headers["Accept-Language"].startswith("ja-JP")
    assert client.headers["If-None-Match"] == '"v1"'


def test_http_fetcher_allows_three_twenty_second_attempts_with_sixty_second_cap() -> None:
    class FakeClock:
        now = 100.0

        def __call__(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.now += seconds

    class TimeoutClient:
        def __init__(self, clock: FakeClock) -> None:
            self.clock = clock
            self.timeouts: list[float] = []

        def get(self, url: str, *, headers: dict[str, str], timeout: float) -> None:
            del headers
            self.timeouts.append(timeout)
            self.clock.sleep(timeout)
            raise httpx.ConnectTimeout("connection timed out", request=httpx.Request("GET", url))

    clock = FakeClock()
    client = TimeoutClient(clock)
    fetcher = HttpFetcher(
        timeout=20,
        max_retries=2,
        request_budget_seconds=60,
        retry_backoff_seconds=(0, 0),
        minimum_host_interval=0,
        client=client,
        _clock=clock,
        _sleeper=clock.sleep,
    )

    with pytest.raises(HttpAttemptsExhausted) as raised:
        fetcher.fetch("https://timeout.example/page")

    assert client.timeouts == pytest.approx([20, 20, 20])
    assert clock.now == pytest.approx(160)
    assert raised.value.attempts == 3
    assert raised.value.is_connection_failure


def test_exhausted_connection_retries_open_same_host_circuit() -> None:
    first = "https://offline.example/first"
    second = "https://www.offline.example/second"
    last_error = httpx.ConnectTimeout(
        "connection timed out",
        request=httpx.Request("GET", first),
    )
    http = FakeHttpFetcher(
        {
            first: HttpAttemptsExhausted(first, 3, last_error),
            second: _response(second, 200, "<main>到達してはいけません</main>"),
        }
    )
    page_fetcher = PageFetcher(http, lambda *_args: "")

    with pytest.raises(FetchProblem, match="host_circuit_open") as opened:
        page_fetcher.fetch(first, _source("offline-first", [first]), {})
    with pytest.raises(FetchProblem, match="host_circuit_open") as skipped:
        page_fetcher.fetch(second, _source("offline-second", [second]), {})

    assert [call[0] for call in http.calls] == [first]
    assert opened.value.cause_code == "ConnectTimeout"
    assert opened.value.attempts == 3
    assert skipped.value.cause_code == "ConnectTimeout"
    assert skipped.value.attempts == 3


def test_different_hosts_are_prefetched_in_parallel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls = [
        "https://parallel-a.example/page",
        "https://parallel-b.example/page",
    ]

    class ParallelProbeFetcher:
        def __init__(self) -> None:
            self.barrier = threading.Barrier(2)
            self.lock = threading.Lock()
            self.active = 0
            self.max_active = 0

        def fetch(
            self,
            url: str,
            etag: str | None = None,
            last_modified: str | None = None,
        ) -> FetchResult:
            del etag, last_modified
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            try:
                self.barrier.wait(timeout=2)
            finally:
                with self.lock:
                    self.active -= 1
            return _response(url, 200, "<main>正常な監視本文です</main>")

    probe = ParallelProbeFetcher()
    monkeypatch.setattr(
        pipeline,
        "_parser_for",
        lambda _source_id: lambda *_args: ([], [], []),
    )
    config = _config(
        _source("parallel-a", [urls[0]]),
        _source("parallel-b", [urls[1]]),
    )

    _, _, alerts = pipeline.run_pipeline(
        config,
        http_fetcher=probe,  # type: ignore[arg-type]
    )

    assert not alerts
    assert probe.max_active == 2


def test_same_host_sources_remain_sequential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls = [
        "https://www.serial.example/first",
        "https://mobile.serial.example/second",
    ]

    class SerialProbeFetcher:
        def __init__(self) -> None:
            self.lock = threading.Lock()
            self.active = 0
            self.max_active = 0

        def fetch(
            self,
            url: str,
            etag: str | None = None,
            last_modified: str | None = None,
        ) -> FetchResult:
            del etag, last_modified
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            try:
                time.sleep(0.03)
            finally:
                with self.lock:
                    self.active -= 1
            return _response(url, 200, "<main>正常な監視本文です</main>")

    probe = SerialProbeFetcher()
    monkeypatch.setattr(
        pipeline,
        "_parser_for",
        lambda _source_id: lambda *_args: ([], [], []),
    )

    _, _, alerts = pipeline.run_pipeline(
        _config(
            _source("serial-a", [urls[0]]),
            _source("serial-b", [urls[1]]),
        ),
        http_fetcher=probe,  # type: ignore[arg-type]
    )

    assert not alerts
    assert probe.max_active == 1


def test_render_mode_uses_configured_expected_content_selector() -> None:
    url = "https://catalog.example/products"
    navigation_only = (
        "<main><h1>商品情報</h1><p>" + "サイト共通ナビゲーション " * 40 + "</p></main>"
    )
    http = FakeHttpFetcher({url: _response(url, 200, navigation_only)})
    rendered_calls: list[str] = []

    def render(render_url: str, _selector: str | None, _timeout: int) -> str:
        rendered_calls.append(render_url)
        return "<main><article class='product-card'>拡張パック商品</article></main>"

    source = replace(
        _source(
            "catalog",
            [url],
            RenderMode.HTTP_THEN_PLAYWRIGHT_IF_EMPTY,
        ),
        render_wait_selector=".product-card",
    )
    result = PageFetcher(http, render).fetch(url, source, {})

    assert result.fetch_method == "playwright"
    assert rendered_calls == [url]


def test_javascript_banner_does_not_replace_substantive_http_content() -> None:
    url = "https://banner.example/lottery"
    substantive = (
        "<main><p>JavaScriptを有効にしてください。</p><article>"
        + "抽選受付期間と対象商品の有効な本文 " * 40
        + "</article></main>"
    )
    http = FakeHttpFetcher({url: _response(url, 200, substantive)})
    rendered_calls: list[str] = []

    def render(render_url: str, _selector: str | None, _timeout: int) -> str:
        rendered_calls.append(render_url)
        return "<main>unused</main>"

    result = PageFetcher(http, render).fetch(
        url,
        _source("banner", [url], RenderMode.HTTP_THEN_BROWSER_IF_SHELL),
        {},
    )

    assert result.fetch_method == "http"
    assert not rendered_calls


def test_discovery_urls_fall_back_until_one_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls = [
        "https://fallback.example/first",
        "https://fallback.example/second",
        "https://fallback.example/third",
    ]
    fetcher = FakeHttpFetcher(
        {
            urls[0]: _response(urls[0], 500, "server error"),
            urls[1]: _response(urls[1], 502, "bad gateway"),
            urls[2]: _response(urls[2], 200, "<main>正常な監視本文です</main>"),
        }
    )
    monkeypatch.setattr(
        pipeline,
        "_parser_for",
        lambda _source_id: lambda *_args: ([], [], []),
    )

    _, _, alerts = pipeline.run_pipeline(
        _config(_source("fallback", urls)),
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert [call[0] for call in fetcher.calls] == urls
    assert not alerts


def test_hobby_station_official_news_falls_back_to_livepocket_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == "livepocket_hobby_station")
    primary, fallback = source.discovery_urls
    fetcher = FakeHttpFetcher(
        {
            primary: _response(primary, 202, ""),
            fallback: _response(
                fallback,
                200,
                "<main><h1>検索結果</h1><p>現在、対象の抽選はありません。</p></main>",
            ),
        }
    )

    _, _, alerts = pipeline.run_pipeline(
        _config(source),
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert [call[0] for call in fetcher.calls] == [primary, fallback]
    assert not alerts


def test_yahoo_success_skips_twstalker_fallback() -> None:
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == "yahoo_realtime_tsutaya_ichinoseki")
    yahoo_url, twstalker_url = source.discovery_urls
    fetcher = FakeHttpFetcher(
        {
            yahoo_url: _response(
                yahoo_url,
                200,
                "<main>一致する情報は見つかりませんでした</main>",
            ),
            twstalker_url: _response(
                twstalker_url,
                200,
                "<main>正常時には取得してはいけません</main>",
            ),
        }
    )

    _, _, alerts = pipeline.run_pipeline(
        _config(source),
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert not alerts
    assert [call[0] for call in fetcher.calls] == [yahoo_url]


@freeze_time("2026-08-16 12:00:00+09:00")
def test_priority_store_yahoo_empty_result_uses_profile_fallback() -> None:
    config = load_config("sites.yaml")
    source = next(
        item for item in config.sources if item.id == "yahoo_realtime_toreca_douraku_sendai"
    )
    (
        yahoo_url,
        yahoo_profile_url,
        yahoo_store_url,
        yahoo_detail_url,
        twstalker_url,
    ) = source.discovery_urls
    status_id = "2084826013847130224"
    twstalker_html = f"""
    <div class="activity-posts">
      <div class="activity-descp"><p>
      ONE PIECEカードゲーム ブースターパック「世界最強の戦士」[OP-17]
      1BOXの抽選販売を開催します。
      応募受付期間：2026年8月15日(土)13:00～8月22日(土)23:59
      </p></div>
      <a href="/Dourakusendai/status/{status_id}">8月15日</a>
    </div>
    """
    fetcher = FakeHttpFetcher(
        {
            yahoo_url: _response(
                yahoo_url,
                200,
                "<main>一致する情報は見つかりませんでした</main>",
            ),
            yahoo_profile_url: _response(
                yahoo_profile_url,
                200,
                """
                <div class="Tweet_TweetContainer__test">
                  <p class="Tweet_body__test">ワンピースカード買取情報更新</p>
                  <time><a href="https://x.com/Dourakusendai/status/2087709916635214248">
                  8月12日</a></time>
                </div>
                """,
            ),
            yahoo_store_url: _response(
                yahoo_store_url,
                200,
                "<main>一致する情報は見つかりませんでした</main>",
            ),
            yahoo_detail_url: _response(
                yahoo_detail_url,
                200,
                "<main>一致する情報は見つかりませんでした</main>",
            ),
            twstalker_url: _response(twstalker_url, 200, twstalker_html),
        }
    )

    cases, _, alerts = pipeline.run_pipeline(
        _config(source),
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert not alerts
    assert [call[0] for call in fetcher.calls] == [
        yahoo_url,
        yahoo_profile_url,
        yahoo_store_url,
        yahoo_detail_url,
        twstalker_url,
    ]
    assert len(cases) == 1
    assert cases[0].retailer_id == "toreca_douraku_sendai"
    assert cases[0].canonical_product_key == "OP-17"


def test_yahoo_ocr_failure_uses_twstalker_and_clears_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == "yahoo_realtime_tsutaya_ichinoseki")
    yahoo_url, twstalker_url = source.discovery_urls
    status_id = "2079755316506599865"
    status_url = f"https://x.com/TSUTAYA19392430/status/{status_id}"
    yahoo_html = f"""
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      【抽選販売について】応募条件などの詳細は添付画像をご確認ください。
      </p>
      <img src="https://rts-pctr.c.yimg.jp/expired-image">
      <time><a href="{status_url}">7月24日</a></time>
    </div>
    """
    twstalker_html = f"""
    <div class="activity-posts">
      <div class="activity-descp"><p>
      ポケカ 拡張パック「ストームエメラルダ」1BOX 抽選販売
      応募受付期間：7/24(金) 10:00から
      </p></div>
      <a href="/TSUTAYA19392430/status/{status_id}">7月24日</a>
    </div>
    """
    fetcher = FakeHttpFetcher(
        {
            yahoo_url: _response(yahoo_url, 200, yahoo_html),
            twstalker_url: _response(twstalker_url, 200, twstalker_html),
        }
    )
    monkeypatch.setattr(
        pipeline,
        "read_image_text",
        lambda _urls: (_ for _ in ()).throw(RuntimeError("expired image")),
    )
    state = MonitorState.load(tmp_path / "monitor_state.json")

    cases, _, alerts = pipeline.run_pipeline(
        _config(source),
        monitor_state=state,
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert [call[0] for call in fetcher.calls] == [yahoo_url, twstalker_url]
    assert len(cases) == 1
    assert cases[0].canonical_product_key == "拡張パック「ストームエメラルダ」"
    assert not alerts
    assert status_url not in state.data["ocr_pending"]


def test_yahoo_all_primary_queries_succeed_without_twstalker() -> None:
    config = load_config("sites.yaml")
    source = next(
        item for item in config.sources if item.id == "yahoo_realtime_premium_bandai_onepiece"
    )
    yahoo_english, yahoo_japanese, twstalker_url = source.discovery_urls
    empty_result = "<main>一致する情報は見つかりませんでした</main>"
    fetcher = FakeHttpFetcher(
        {
            yahoo_english: _response(yahoo_english, 200, empty_result),
            yahoo_japanese: _response(yahoo_japanese, 200, empty_result),
            twstalker_url: _response(
                twstalker_url,
                200,
                "<main>正常時には取得してはいけません</main>",
            ),
        }
    )

    _, _, alerts = pipeline.run_pipeline(
        _config(source),
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert not alerts
    assert [call[0] for call in fetcher.calls] == [
        yahoo_english,
        yahoo_japanese,
    ]


def test_yahoo_fetch_failure_uses_twstalker_fallback() -> None:
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == "yahoo_realtime_tsutaya_ichinoseki")
    yahoo_url, twstalker_url = source.discovery_urls
    fetcher = FakeHttpFetcher(
        {
            yahoo_url: _response(yahoo_url, 500, "<main>server error</main>"),
            twstalker_url: _response(
                twstalker_url,
                200,
                "<main>Twstalkerの代替ページを正常に読み込みました</main>",
            ),
        }
    )

    _, _, alerts = pipeline.run_pipeline(
        _config(source),
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert not alerts
    assert [call[0] for call in fetcher.calls] == [yahoo_url, twstalker_url]


def test_yahoo_http_success_with_broken_structure_uses_twstalker() -> None:
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == "yahoo_realtime_tsutaya_ichinoseki")
    yahoo_url, twstalker_url = source.discovery_urls
    fetcher = FakeHttpFetcher(
        {
            yahoo_url: _response(
                yahoo_url,
                200,
                "<main>HTTPは成功したが検索結果部分が消えています</main>",
            ),
            twstalker_url: _response(
                twstalker_url,
                200,
                "<main>Twstalker検索結果</main>",
            ),
        }
    )

    _, _, alerts = pipeline.run_pipeline(
        _config(source),
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert not alerts
    assert [call[0] for call in fetcher.calls] == [yahoo_url, twstalker_url]


def test_yahoo_parser_failure_uses_twstalker_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == "yahoo_realtime_tsutaya_ichinoseki")
    yahoo_url, twstalker_url = source.discovery_urls
    fetcher = FakeHttpFetcher(
        {
            yahoo_url: _response(
                yahoo_url,
                200,
                "<main>一致する情報は見つかりませんでした</main>",
            ),
            twstalker_url: _response(
                twstalker_url,
                200,
                "<main>Twstalker検索結果</main>",
            ),
        }
    )

    def parser(
        _html: str,
        url: str,
        *_args: Any,
        **_kwargs: Any,
    ) -> tuple[list[Any], list[Any], list[Any]]:
        if url == yahoo_url:
            raise ValueError("Yahoo parser structure changed")
        return [], [], []

    monkeypatch.setattr(pipeline, "parse_yahoo_realtime", parser)

    _, _, alerts = pipeline.run_pipeline(
        _config(source),
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert not alerts
    assert [call[0] for call in fetcher.calls] == [yahoo_url, twstalker_url]


def test_yahoo_empty_direct_post_fallback_continues_to_profile_mirror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config("sites.yaml")
    source = next(
        item for item in config.sources if item.id == "yahoo_realtime_seagull_common"
    )
    yahoo_lottery, yahoo_account, oembed_url, twstalker_url = source.discovery_urls
    empty_result = "<main>一致する情報は見つかりませんでした</main>"
    fetcher = FakeHttpFetcher(
        {
            yahoo_lottery: _response(yahoo_lottery, 200, empty_result),
            yahoo_account: _response(yahoo_account, 200, empty_result),
            oembed_url: _response(oembed_url, 200, '{"html":""}'),
            twstalker_url: _response(
                twstalker_url,
                200,
                "<main>プロフィールミラーにも候補はありません</main>",
            ),
        }
    )
    monkeypatch.setattr(
        pipeline,
        "parse_yahoo_realtime",
        lambda *_args, **_kwargs: ([], [], []),
    )

    _, _, alerts = pipeline.run_pipeline(
        _config(source),
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert not alerts
    assert [call[0] for call in fetcher.calls] == [
        yahoo_lottery,
        yahoo_account,
        oembed_url,
        twstalker_url,
    ]


def test_yahoo_repair_url_remains_independent_from_twstalker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == "yahoo_realtime_tsutaya_ichinoseki")
    yahoo_url, twstalker_url = source.discovery_urls
    repair_url = "https://search.yahoo.co.jp/realtime/search/tweet/2080582562012119398?detail=1"
    fetcher = FakeHttpFetcher(
        {
            yahoo_url: _response(
                yahoo_url,
                200,
                "<main>一致する情報は見つかりませんでした</main>",
            ),
            repair_url: _response(repair_url, 200, "<main>個別投稿の再確認結果</main>"),
            twstalker_url: _response(
                twstalker_url,
                200,
                "<main>正常時には取得してはいけません</main>",
            ),
        }
    )
    state = MonitorState.load(tmp_path / "monitor_state.json")
    monkeypatch.setattr(
        pipeline,
        "yahoo_repair_discovery_urls",
        lambda *_args: [repair_url],
    )

    _, _, alerts = pipeline.run_pipeline(
        _config(source),
        monitor_state=state,
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert not alerts
    assert [call[0] for call in fetcher.calls] == [yahoo_url, repair_url]


def test_same_host_circuit_breaker_stops_remaining_sources() -> None:
    urls = [
        "https://www.blocked.example/first",
        "https://blocked.example/second",
        "https://mobile.blocked.example/third",
    ]
    fetcher = FakeHttpFetcher(
        {
            urls[0]: _response(urls[0], 403, "<html>forbidden</html>"),
            urls[1]: _response(
                urls[1],
                503,
                "<html><p>Checking your browser</p><p>Cloudflare Ray ID</p></html>",
            ),
            urls[2]: _response(urls[2], 403, "<html>forbidden</html>"),
        }
    )
    sources = [_source(f"blocked-{index}", [url]) for index, url in enumerate(urls)]

    _, _, alerts = pipeline.run_pipeline(
        _config(*sources),
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert [call[0] for call in fetcher.calls] == urls[:2]
    assert [alert.reason_code for alert in alerts] == ["host_circuit_open"]
    assert alerts[0].source_id == "provider:blocked.example"
    assert "連続2回" in alerts[0].change_summary
    assert "Cloudflare" in alerts[0].change_summary


def test_healthy_fallback_marks_primary_degraded_without_discord_alert(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary_url = "https://blocked-primary.example/lottery"
    fallback_url = "https://healthy-fallback.example/lottery"
    primary = replace(
        _source("primary", [primary_url]),
        fallback_source_ids=["fallback"],
    )
    fallback = _source("fallback", [fallback_url])
    fetcher = FakeHttpFetcher(
        {
            primary_url: _response(primary_url, 403, "<main>forbidden</main>"),
            fallback_url: _response(
                fallback_url,
                200,
                "<main>代替経路は正常です</main>",
            ),
        }
    )
    monkeypatch.setattr(
        pipeline,
        "_parser_for",
        lambda _source_id: lambda *_args: ([], [], []),
    )
    state = MonitorState.load(tmp_path / "monitor_state.json")

    _, _, alerts = pipeline.run_pipeline(
        _config(primary, fallback),
        monitor_state=state,
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert not alerts
    assert state.data["monitors"]["primary"]["outcome"] == "degraded"
    assert state.data["monitors"]["primary"]["coverage_status"] == ("covered_by_fallback")
    assert state.data["monitors"]["primary"]["healthy_fallbacks"] == ["fallback"]
    assert state.data["last_run_summary"]["degraded_monitors"] == 1
    assert state.data["last_run_summary"]["failed_monitors"] == 0
    assert state.data["last_run_summary"]["source_failures"] == 1


def test_failed_fallback_keeps_primary_transport_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary_url = "https://blocked-primary.example/lottery"
    fallback_url = "https://blocked-fallback.example/lottery"
    primary = replace(
        _source("primary", [primary_url]),
        fallback_source_ids=["fallback"],
    )
    fallback = _source("fallback", [fallback_url])
    fetcher = FakeHttpFetcher(
        {
            primary_url: _response(primary_url, 500, "<main>server error</main>"),
            fallback_url: _response(fallback_url, 500, "<main>server error</main>"),
        }
    )
    monkeypatch.setattr(
        pipeline,
        "_parser_for",
        lambda _source_id: lambda *_args: ([], [], []),
    )

    _, _, alerts = pipeline.run_pipeline(
        _config(primary, fallback),
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert {alert.source_id for alert in alerts} == {"primary", "fallback"}


def test_conditional_get_reuses_etag_and_last_modified() -> None:
    url = "https://cache.example/page"
    http = FakeHttpFetcher({url: _response(url, 304, "")})
    cache: dict[str, object] = {
        url: {
            "etag": '"v1"',
            "last_modified": "Sat, 25 Jul 2026 00:00:00 GMT",
        }
    }

    result = PageFetcher(http, lambda *_args: "").fetch(
        url,
        _source("cached", [url]),
        cache,
    )

    assert result.not_modified
    assert http.calls == [(url, '"v1"', "Sat, 25 Jul 2026 00:00:00 GMT")]
    assert isinstance(cache[url], dict)
    assert cache[url]["checked_at"]


def test_conditional_get_can_be_disabled() -> None:
    url = "https://cache.example/disabled"
    http = FakeHttpFetcher(
        {
            url: _response(
                url,
                200,
                "<main>条件付きGETを使わない通常本文です</main>",
                ETag='"v2"',
            )
        }
    )
    cache: dict[str, object] = {url: {"etag": '"v1"'}}

    result = PageFetcher(
        http,
        lambda *_args: "",
        conditional_get=False,
    ).fetch(url, _source("uncached", [url]), cache)

    assert result.fetch_method == "http"
    assert http.calls == [(url, None, None)]
    assert cache == {url: {"etag": '"v1"'}}


def test_source_can_disable_conditional_get() -> None:
    url = "https://cache.example/source-disabled"
    http = FakeHttpFetcher(
        {
            url: _response(
                url,
                200,
                "<main>キャッシュせず毎回確認する本文です</main>",
                ETag='"v2"',
            )
        }
    )
    cache: dict[str, object] = {url: {"etag": '"blocked-shell"'}}
    source = replace(
        _source("source-uncached", [url]),
        parser_options={"disable_conditional_get": True},
    )

    result = PageFetcher(http, lambda *_args: "").fetch(url, source, cache)

    assert result.fetch_method == "http"
    assert http.calls == [(url, None, None)]
    assert cache == {url: {"etag": '"blocked-shell"'}}


@freeze_time("2026-08-03 12:00:00+09:00")
def test_yahoo_provisional_case_is_revisited_from_detail_page(tmp_path) -> None:
    base = load_config("sites.yaml")
    source = next(item for item in base.sources if item.id == "yahoo_realtime_geo_official")
    root_url = source.discovery_urls[0]
    status_id = "2080582562012119398"
    status_url = f"https://x.com/GEO_official/status/{status_id}"
    detail_url = (
        f"https://search.yahoo.co.jp/realtime/search/tweet/{status_id}?detail=1&ifr=tl_twdtl&rkf=1"
    )
    detail_html = f"""
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      #ポケモンカードゲーム 拡張パック ホワイトフレアの
      <em>抽選</em> 販売
      【抽選 受付期間】8/3(月) 11:00から8/6(木) 17:59まで
      【当選者への連絡日】8/20(木)
      </p>
      <time><a href="{status_url}">7月25日</a></time>
    </div>
    """
    fetcher = FakeHttpFetcher(
        {
            root_url: _response(
                root_url,
                200,
                "<main>一致する情報は見つかりませんでした</main>",
            ),
            detail_url: _response(detail_url, 200, detail_html),
        }
    )
    state = MonitorState.load(tmp_path / "monitor_state.json")
    state.data["seen_cases"]["provisional"] = {
        "game_id": "pokemon_card",
        "retailer_id": "geo",
        "product_name": "拡張パック「当選者への連絡日」",
        "source_url": status_url,
    }

    cases, _, alerts = pipeline.run_pipeline(
        _config(source),
        monitor_state=state,
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert not alerts
    assert [call[0] for call in fetcher.calls] == [root_url, detail_url]
    assert len(cases) == 1
    assert cases[0].product_name == "拡張パック「ホワイトフレア」"


def test_ocr_failure_is_pending_before_repeated_alert() -> None:
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == "yahoo_realtime_yorozuya_morioka")
    status_url = "https://x.com/yorozuya_card/status/2079734608745201729"
    html = f"""
    <div class="Tweet_TweetContainer__changed">
      <p class="Tweet_body__changed">【抽選販売について】詳細は画像をご確認ください。
      応募にはこのポストのリポストが必要です。</p>
      <img src="https://pbs.twimg.com/media/test.jpg">
      <time><a href="{status_url}">8時間前</a></time>
    </div>
    """
    pending: dict[str, object] = {}

    def failing_ocr(_urls: list[str]) -> str:
        raise RuntimeError("temporary failure")

    first_cases, _, first_alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        config,
        date(2026, 7, 22),
        failing_ocr,
        {},
        [],
        pending,
        {},
        "run-1",
    )
    second_cases, _, second_alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        config,
        date(2026, 7, 22),
        failing_ocr,
        {},
        [],
        pending,
        {},
        "run-1",
    )
    third_cases, _, third_alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        config,
        date(2026, 7, 22),
        failing_ocr,
        {},
        [],
        pending,
        {},
        "run-2",
    )

    assert not first_cases and not second_cases and not third_cases
    assert not first_alerts
    assert not second_alerts
    assert pending[status_url]["attempts"] == 2  # type: ignore[index]
    assert [alert.reason_code for alert in third_alerts] == ["yahoo_image_ocr_repeated_failure"]


def test_unsupported_game_is_not_parsed() -> None:
    config = load_config("sites.yaml")
    geo = next(source for source in config.sources if source.id == "geo")
    unsupported_geo = replace(
        geo,
        supported_games={
            **geo.supported_games,
            "one_piece_card": GameSupport.UNSUPPORTED,
        },
    )
    html = """
    <article>
      <h1>ONE PIECEカードゲーム ブースターパック「世界最強の戦士」抽選販売</h1>
      <p>1BOX 応募期間 2026年8月3日 11:00から</p>
    </article>
    """

    cases, releases, alerts = parse_generic(
        html,
        "https://geo-online.co.jp/news/unsupported",
        unsupported_geo,
        config,
    )

    assert not cases
    assert not releases
    assert not alerts
    assert not unsupported_geo.supports("one_piece_card")


def test_validate_config_rejects_unknown_support_status(tmp_path) -> None:
    original = Path("sites.yaml").read_text(encoding="utf-8")
    invalid = original.replace(
        "pokemon_card: verified",
        "pokemon_card: typo_status",
        1,
    )
    path = tmp_path / "invalid-sites.yaml"
    path.write_text(invalid, encoding="utf-8")

    with pytest.raises(ConfigError, match="bad supported_games status"):
        load_config(path)


def test_validate_config_rejects_unknown_fallback_source(tmp_path: Path) -> None:
    invalid = yaml.safe_load(Path("sites.yaml").read_text(encoding="utf-8"))
    source = next(item for item in invalid["sources"] if item["id"] == "geo")
    source["fallback_source_ids"] = ["missing_source"]
    path = tmp_path / "invalid-sites.yaml"
    path.write_text(yaml.safe_dump(invalid, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ConfigError, match="unknown fallback source"):
        load_config(path)


def test_validate_config_requires_verified_game_fallback_coverage(
    tmp_path: Path,
) -> None:
    invalid = yaml.safe_load(Path("sites.yaml").read_text(encoding="utf-8"))
    source = next(item for item in invalid["sources"] if item["id"] == "geo")
    source["fallback_source_ids"] = ["snkrdunk_onepiece"]
    path = tmp_path / "invalid-sites.yaml"
    path.write_text(yaml.safe_dump(invalid, allow_unicode=True), encoding="utf-8")

    with pytest.raises(
        ConfigError,
        match="fallback sources do not cover verified games",
    ):
        load_config(path)


def test_prospective_game_is_not_accepted_as_verified_fallback(
    tmp_path: Path,
) -> None:
    invalid = yaml.safe_load(Path("sites.yaml").read_text(encoding="utf-8"))
    source = next(item for item in invalid["sources"] if item["id"] == "geo")
    source["fallback_source_ids"] = ["yamada_denki"]
    path = tmp_path / "invalid-sites.yaml"
    path.write_text(yaml.safe_dump(invalid, allow_unicode=True), encoding="utf-8")

    with pytest.raises(
        ConfigError,
        match="fallback sources do not cover verified games",
    ):
        load_config(path)


def test_access_limited_production_sources_declare_healthy_alternatives() -> None:
    config = load_config("sites.yaml")
    by_id = {source.id: source for source in config.sources}

    assert by_id["geo"].fallback_source_ids == ["yahoo_realtime_geo_official"]
    assert by_id["yamada_denki"].fallback_source_ids == [
        "snkrdunk_pokemon",
        "snkrdunk_onepiece",
    ]
    assert by_id["kojima"].fallback_source_ids == [
        "snkrdunk_pokemon",
        "snkrdunk_onepiece",
    ]
    assert by_id["yahoo_realtime_yamada_secondary"].source_tier == (SourceTier.SECONDARY)
    assert by_id["yahoo_realtime_kojima_secondary"].source_tier == (SourceTier.SECONDARY)
    assert by_id["pokemon_center_store"].fallback_source_ids == [
        "yahoo_realtime_pokemon_center_store"
    ]
    assert by_id["yodobashi"].fallback_source_ids == ["yahoo_realtime_yodobashi"]
    assert by_id["konami_style_yugioh"].fallback_source_ids == ["yahoo_realtime_konami_style"]
    assert by_id["takaratomy_mall_lorcana"].render_mode == (
        RenderMode.HTTP_THEN_BROWSER_ONCE_NO_CHALLENGE_BYPASS
    )
    assert len(by_id["takaratomy_mall_lorcana"].discovery_urls) == 2
    assert by_id["takaratomy_mall_lorcana"].fallback_source_ids == [
        "yahoo_realtime_lorcana_official"
    ]
    assert by_id["kids_republic"].fallback_source_ids == [
        "snkrdunk_pokemon",
        "yahoo_realtime_kids_republic_official",
    ]
    assert by_id["kids_republic"].supported_games["yu_gi_oh"] == (GameSupport.VERIFIED)
    assert by_id["aeon_style_online"].fallback_source_ids == ["snkrdunk_pokemon"]
    assert by_id["dmm_hobby_lottery"].fallback_source_ids == [
        "yahoo_realtime_dmm_tsuhan",
        "nyuka_now_fullcomp_livepocket",
    ]
    assert by_id["hobby_search_lottery"].fallback_source_ids == ["snkrdunk_pokemon"]
    assert by_id["edion_online_lottery"].fallback_source_ids == ["yahoo_realtime_edion"]
    assert by_id["hobbylink_japan_lottery"].fallback_source_ids == [
        "yahoo_realtime_hobbylink_japan"
    ]
    assert by_id["nyuka_now_premium_bandai_onepiece"].fallback_source_ids == [
        "yahoo_realtime_premium_bandai_onepiece",
        "premium_bandai_onepiece",
    ]


def test_validate_config_rejects_invalid_request_budget(tmp_path) -> None:
    path = tmp_path / "sites.yaml"
    path.write_text(
        """
schema_version: 2
system:
  request_budget_seconds: 0
games: {}
sources: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="request_budget_seconds"):
        load_config(path, private_config_path="")


def test_production_config_uses_three_attempts_and_bounded_host_parallelism() -> None:
    system = load_config("sites.yaml").system

    assert system["request_timeout_seconds"] == 20
    assert system["request_budget_seconds"] == 60
    assert system["max_retries"] == 2
    assert system["retry_backoff_seconds"] == [0, 0]
    assert system["max_parallel_hosts"] == 6


def test_validate_config_rejects_excessive_parallel_hosts(tmp_path) -> None:
    path = tmp_path / "sites.yaml"
    path.write_text(
        """
schema_version: 2
system:
  max_parallel_hosts: 17
games: {}
sources: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="max_parallel_hosts"):
        load_config(path, private_config_path="")


def test_omitted_year_uses_nearby_year_across_new_year() -> None:
    next_year = parse_first_datetime("1/1 10:00", date(2026, 12, 31))
    previous_year = parse_first_datetime("12/31 23:00", date(2027, 1, 1))

    assert next_year.value == datetime(
        2027,
        1,
        1,
        10,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )
    assert previous_year.value == datetime(
        2026,
        12,
        31,
        23,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )
