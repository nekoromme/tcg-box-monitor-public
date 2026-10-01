from __future__ import annotations

import sys
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from freezegun import freeze_time

from tcg_monitor.browser_fetch import fetch_rendered_html
from tcg_monitor.classifier import canonical_product_key
from tcg_monitor.cli import (
    _cleanup_confirmed_false_positive_cases,
    _lottery_discord_description,
    _opportunity_uses_calendar,
    _prepare_cases,
)
from tcg_monitor.config import load_config
from tcg_monitor.fetching import FetchProblem, PageFetcher, PageKind, classify_page
from tcg_monitor.http_client import FetchResult, HttpAttemptsExhausted
from tcg_monitor.models import OpportunityKind, Release, SourceTier
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.pipeline import run_pipeline
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState

CONFIG = load_config("sites.yaml")
SOURCE = next(s for s in CONFIG.sources if s.id == "yahoo_realtime_lorcana_official")
MALL = next(s for s in CONFIG.sources if s.id == "takaratomy_mall_lorcana")
NAME = "ブースターパック「ハイペリアシティ」"
RELEASE = Release(
    "lorcana", NAME, "ブースターパック", canonical_product_key(CONFIG.games["lorcana"], NAME),
    date(2026, 10, 16), None,
    "https://www.takaratomy.co.jp/products/disneylorcana/product/hyperia-city/booster-pack/",
    "https://www.takaratomy.co.jp/products/disneylorcana/product/hyperia-city/booster-pack/",
    SourceTier.OFFICIAL, "lorcana_official_booster_detail", "high",
).with_id()


def _post(body: str, status_id: str = "2102737947799736768", link: str = "") -> str:
    return (
        '<div class="Tweet_TweetContainer__test"><p class="Tweet_body__test">'
        f'{body}<a href="{link}">商品情報</a></p>'
        f'<time><a href="https://x.com/DisneyLOR_JP/status/{status_id}">9月24日</a></time></div>'
    )


def _parse(html: str):
    return parse_yahoo_realtime(
        html, SOURCE.discovery_urls[0], SOURCE, CONFIG, date(2026, 9, 24),
        known_releases=[RELEASE],
    )


@pytest.mark.parametrize("body", [
    "【お知らせ💌】10月16日（金）発売予定 #ディズニーロルカナ「ハイぺリアシティ」"
    "9月24日(木)から予約開始！",
    "10月16日発売予定 ロルカナ ブースターパック「ハイペリアシティ」"
    "9/24(木)から予約 開始！ ボックス同梱特典も公開",
])
def test_real_reservation_date_and_catalog_title_are_used(body: str) -> None:
    cases, releases, alerts = _parse(_post(body))
    assert not releases and not alerts
    assert len(cases) == 1
    assert cases[0].start_at == date(2026, 9, 24)  # 発売日の10/16を使わない。
    assert cases[0].product_name == NAME
    assert cases[0].opportunity_kind == OpportunityKind.DIRECT_SALE
    assert cases[0].retailer_id == "lorcana_official"
    assert cases[0].official_url == RELEASE.official_url
    description = _lottery_discord_description(cases[0])
    assert "公式商品情報・告知ページ" in description
    assert "各店の在庫・受付状況は未確認" in description


def test_missing_reservation_date_is_not_promoted_from_release_date() -> None:
    cases, _, alerts = _parse(_post(
        "【お知らせ💌】10月16日発売予定 ディズニーロルカナ「ハイぺリアシティ」予約開始しました！",
        "2102774999895670970",
    ))
    assert not alerts
    assert cases[0].start_at == date(2026, 9, 24)
    assert cases[0].opportunity_kind == OpportunityKind.DIRECT_SALE_SEEN
    assert not _opportunity_uses_calendar(cases[0])
    assert "告知日（開始日時不明）" in _lottery_discord_description(cases[0])


def test_advance_and_repeated_notices_merge_into_one_confirmed_reservation(tmp_path: Path) -> None:
    unknown, _, _ = _parse(_post(
        "10月16日発売予定 ロルカナ「ハイぺリアシティ」まもなく予約開始",
        "2102774999895670970",
    ))
    exact, _, _ = _parse(_post(
        "10月16日発売予定 ロルカナ「ハイぺリアシティ」9月24日から予約開始",
    ))
    assert unknown[0].case_id == exact[0].case_id
    merged, alerts = merge_lotteries([*unknown, *exact])
    assert not alerts and merged == exact
    # 両検索で同じ告知が出ても、確定日を日付なし投稿で上書きしない。
    combined, _, _ = _parse(
        _post("10月16日発売予定 ロルカナ「ハイぺリアシティ」9月24日から予約開始")
        + _post("10月16日発売予定 ロルカナ「ハイぺリアシティ」予約開始しました！",
                "2102774999895670970")
    )
    assert combined == exact
    state = MonitorState.load(tmp_path / "state.json")
    state.data["seen_cases"][unknown[0].case_id] = {
        **asdict(unknown[0]), "start_at": unknown[0].start_at.isoformat(),
    }
    state.mark_delivered(f"lottery:started:{unknown[0].case_id}")
    assert _prepare_cases(state, exact)[1] == 0
    assert state.delivered(f"lottery:started:{exact[0].case_id}")


def test_mall_specific_post_keeps_real_store_identity_and_merges_with_direct_route() -> None:
    mall_url = "https://takaratomymall.jp/shop/g/g8000000207587/"
    cases, _, alerts = _parse(_post(
        "10月16日発売予定 ロルカナ ブースターパック「ハイぺリアシティ」"
        "9月24日から予約開始 タカラトミーモールでも受付", link=mall_url,
    ))
    assert not alerts
    assert cases[0].retailer_id == "takaratomy_mall"
    assert cases[0].official_url == mall_url
    direct = replace(cases[0], source_tier=SourceTier.OFFICIAL, source_url=mall_url,
                     extraction_method="takaratomy_mall_labelled_period", case_id="").with_id()
    assert merge_lotteries([*cases, direct])[0] == [direct]


def test_later_sale_is_not_suppressed_by_the_initial_reservation() -> None:
    reserved, _, _ = _parse(_post(
        "ロルカナ ブースターパック「ハイペリアシティ」9月24日から予約開始",
    ))
    restocked, _, alerts = _parse(_post(
        "ロルカナ ブースターパック「ハイペリアシティ」10月1日から再販開始",
        "2102774999895670970",
    ))
    assert not alerts
    assert restocked[0].case_id != reserved[0].case_id
    assert len(merge_lotteries([*reserved, *restocked])[0]) == 2


def test_mall_lottery_is_attributed_to_the_mall() -> None:
    cases, _, alerts = _parse(_post(
        "タカラトミーモール ロルカナ ブースターパック「ハイペリアシティ」"
        "1BOX抽選販売 応募受付開始 受付期間：9月24日から9月30日まで",
    ))
    assert not alerts
    assert cases[0].retailer_id == "takaratomy_mall"
    assert cases[0].opportunity_kind == OpportunityKind.LOTTERY


def test_only_two_confirmed_wrong_reservation_events_are_removed(tmp_path: Path) -> None:
    records = CONFIG.system["runtime"]["confirmed_false_positive_cases"]
    wrong = {k: v for k, v in records.items() if v["retailer_id"] == "lorcana_official"}
    assert len(wrong) == 2
    state = MonitorState.load(tmp_path / "state.json")
    for case_id, record in wrong.items():
        state.data["seen_cases"][case_id] = dict(record)
        state.data["calendar_sync"][f"lottery:{case_id}"] = {"event_id": record["event_id"]}
    state.data["seen_releases"][RELEASE.release_id] = {"release_date": "2026-10-16"}
    calendar = Mock()
    calendar.delete_owned_event.return_value = {"status": "deleted"}
    results = _cleanup_confirmed_false_positive_cases(state, calendar, wrong)
    assert len(results) == 2 and calendar.delete_owned_event.call_count == 2
    assert not state.data["seen_cases"]
    assert state.data["seen_releases"][RELEASE.release_id]["release_date"] == "2026-10-16"


@pytest.mark.parametrize("body", [
    "ロルカナ 大会事前予約開始 10月16日開催 ブースターパック「ハイペリアシティ」",
    "10月16日発売予定 ロルカナ スリーブ「ハイペリアシティ」予約開始",
])
def test_tournaments_and_supplies_do_not_become_booster_reservations(body: str) -> None:
    cases, _, alerts = _parse(_post(body))
    assert not cases and not alerts


@freeze_time("2026-09-24 12:00:00+09:00")
def test_existing_routes_without_polling_disabled_mall(tmp_path: Path) -> None:
    html = _post("10月16日発売予定 ロルカナ ブースターパック「ハイペリアシティ」"
                 "9月24日から予約開始")
    calls: list[str] = []

    class Fetcher:
        def fetch(self, url, **_kwargs):
            assert "takaratomymall.jp" not in url
            calls.append(url)
            return FetchResult(url, 200, html, {})

    state = MonitorState.load(tmp_path / "state.json")
    config = replace(CONFIG, sources=[MALL, SOURCE])
    cases, releases, alerts = run_pipeline(config, monitor_state=state, http_fetcher=Fetcher())
    assert not releases and not alerts
    assert len(cases) == 1
    assert len(calls) == 2  # 既存のキーワード検索とアカウント検索。監視元を増やさない。
    assert set(state.data["monitors"]) == {SOURCE.id}
    assert not MALL.enabled


def test_browser_network_failure_preserves_the_initial_http_timeout(tmp_path: Path) -> None:
    url = MALL.discovery_urls[0]

    class Fetcher:
        def fetch(self, _url, **_kwargs):
            raise HttpAttemptsExhausted(url, 3, httpx.ReadTimeout("read timed out"))

    def render(*_args):
        raise RuntimeError("Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR at private-url?token=secret")

    fetcher = PageFetcher(Fetcher(), render)
    with pytest.raises(FetchProblem) as failure:
        fetcher.fetch(url, MALL, {})
    assert failure.value.cause_code == "ERR_HTTP2_PROTOCOL_ERROR"
    assert failure.value.prior_cause_code == "ReadTimeout"
    assert failure.value.prior_attempts == 3
    assert "secret" not in str(failure.value)
    state = MonitorState.load(tmp_path / "state.json")
    run_pipeline(replace(CONFIG, sources=[replace(MALL, enabled=True, discovery_urls=[url])]),
                 monitor_state=state, http_fetcher=Fetcher(), browser_fetcher=render)
    record = state.data["monitors"][MALL.id]
    assert record["failure_cause"] == "ERR_HTTP2_PROTOCOL_ERROR"
    assert record["prior_failure_cause"] == "ReadTimeout"
    assert record["routes"][url]["prior_failure_attempts"] == 3


def test_waiting_room_is_returned_before_waiting_for_missing_product_links(monkeypatch) -> None:
    html = ('<title>Queue-it</title><meta id="queue-it_log">'
            '<script data-queueit-c="takaratomy"></script>'
            '<p>ただいまサイトが混みあっております</p>')
    calls: list[str] = []

    class Page:
        def goto(self, *_args, **_kwargs):
            calls.append("goto")

        def content(self):
            return html

        def wait_for_selector(self, *_args, **_kwargs):
            pytest.fail("待合室で商品リンクを待ってはいけない")

    browser = SimpleNamespace(version="123", new_page=lambda **_kw: Page(),
                              close=lambda: calls.append("close"))

    class Context:
        def __enter__(self):
            return SimpleNamespace(chromium=SimpleNamespace(launch=lambda **_kw: browser))

        def __exit__(self, *_args):
            return False

    monkeypatch.setitem(
        sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=Context),
    )
    returned = fetch_rendered_html(MALL.discovery_urls[0], MALL.render_wait_selector)
    assert classify_page(returned) == PageKind.CHALLENGE
    assert calls == ["goto", "close"]
