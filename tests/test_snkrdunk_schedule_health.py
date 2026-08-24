from __future__ import annotations

from dataclasses import replace

from tcg_monitor.config import load_config
from tcg_monitor.http_client import FetchResult
from tcg_monitor.parsers.snkrdunk import (
    discover_snkrdunk_article_urls,
    is_snkrdunk_schedule_healthy_without_candidates,
)
from tcg_monitor.pipeline import run_pipeline

SCHEDULE_URL = "https://snkrdunk.com/articles/14006/"


def _source():  # type: ignore[no-untyped-def]
    return next(
        source
        for source in load_config("sites.yaml").sources
        if source.id == "snkrdunk_onepiece"
    )


def _idle_schedule_html() -> str:
    return """
    <h1>【ワンピースカード】2026年新弾発売スケジュール</h1>
    <h2 id="schedule2026">2026年の発売スケジュール</h2>
    <h2 id="OP-17">ブースターパック「世界最強の戦士」</h2>
    <a href="https://snkrdunk.com/articles/32598/?slide=right">
      【ワンピースカード】世界最強の戦士の当たりランキング/買取相場
    </a>
    """


def test_schedule_article_url_discards_presentation_query() -> None:
    source = _source()
    html = """
    <h1>【ワンピースカード】2026年新弾発売スケジュール</h1>
    <a href="https://snkrdunk.com/articles/33123/?slide=right">
      【ワンピースカード】次弾の予約・抽選情報まとめ
    </a>
    """

    assert discover_snkrdunk_article_urls(html, SCHEDULE_URL, source) == [
        "https://snkrdunk.com/articles/33123/"
    ]


def test_schedule_after_release_is_healthy_without_lottery_article() -> None:
    source = _source()
    html = _idle_schedule_html()

    assert discover_snkrdunk_article_urls(html, SCHEDULE_URL, source) == []
    assert is_snkrdunk_schedule_healthy_without_candidates(html, source)


def test_unreadable_lottery_link_is_not_treated_as_healthy_idle() -> None:
    source = _source()
    html = """
    <h1>【ワンピースカード】2026年新弾発売スケジュール</h1>
    <h2 id="OP-18">ブースターパック「次弾」</h2>
    <a href="/magazine/next-lottery">
      【ワンピースカード】次弾の予約・抽選情報まとめ
    </a>
    """

    assert discover_snkrdunk_article_urls(html, SCHEDULE_URL, source) == []
    assert not is_snkrdunk_schedule_healthy_without_candidates(html, source)


class _Fetcher:
    def __init__(self, html: str) -> None:
        self.html = html

    def fetch(
        self,
        url: str,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        del etag, last_modified
        return FetchResult(url, 200, self.html, {})


def _run_schedule(html: str):  # type: ignore[no-untyped-def]
    config = load_config("sites.yaml")
    source = replace(_source(), discovery_urls=[SCHEDULE_URL])
    config = replace(
        config,
        sources=[source],
        system={
            **config.system,
            "minimum_host_interval_seconds": 0,
            "request_timeout_seconds": 1,
        },
    )
    return run_pipeline(config, http_fetcher=_Fetcher(html))  # type: ignore[arg-type]


def test_pipeline_suppresses_idle_schedule_alert_but_keeps_real_breakage() -> None:
    cases, releases, alerts = _run_schedule(_idle_schedule_html())
    assert not cases
    assert not releases
    assert not alerts

    broken_html = """
    <h1>【ワンピースカード】2026年新弾発売スケジュール</h1>
    <p>商品区画を読み込めませんでした</p>
    """
    cases, releases, alerts = _run_schedule(broken_html)
    assert not cases
    assert not releases
    assert len(alerts) == 1
    assert alerts[0].reason_code == "discovery_links_missing"

