from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from tcg_monitor.config import load_config
from tcg_monitor.http_client import FetchResult
from tcg_monitor.parsers.local_lottery import (
    discover_livepocket_event_urls,
    parse_livepocket_event,
)
from tcg_monitor.pipeline import run_pipeline
from tcg_monitor.state import MonitorState

FIXTURES = Path(__file__).parent / "fixtures" / "wakuya"
EVENT = "https://livepocket.jp/e/2q34tryqw98dvhasjkl-jgh12u89yru"


def settings():
    config = load_config("sites.yaml")
    source = next(s for s in config.sources if s.id == "livepocket_tsutaya_wakuya")
    return config, source


def test_unlisted_event_is_discovered_without_x_and_uses_official_dates():
    config, source = settings()
    urls = discover_livepocket_event_urls(
        (FIXTURES / "index.html").read_text(), source.discovery_urls[0], source, config,
    )
    assert urls == [EVENT]
    cases, _, alerts = parse_livepocket_event(
        (FIXTURES / "event.html").read_text(), EVENT, source, config,
    )
    assert not alerts
    assert len(cases) == 1
    case = cases[0]
    assert case.canonical_product_key == "OP-18"
    assert case.retailer_id == "tsutaya_wakuya"
    assert case.start_at == datetime(2026, 11, 7, 12, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert case.end_at == datetime(2026, 11, 10, 21, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert case.official_url == EVENT
    assert parse_livepocket_event(
        (FIXTURES / "event.html").read_text(), EVENT, source, config,
    )[0][0].case_id == case.case_id


@pytest.mark.parametrize("replacement", ["<h1>別店舗</h1><div id='list'></div>",
                                         "<h1>TSUTAYA涌谷店</h1><p>構造変更</p>"])
def test_index_structure_and_store_mismatch_are_errors(replacement):
    config, source = settings()
    with pytest.raises(ValueError):
        discover_livepocket_event_urls(replacement, source.discovery_urls[0], source, config)


def test_empty_index_and_non_box_do_not_notify():
    config, source = settings()
    html = '<h1>TSUTAYA涌谷店</h1><div id="list"></div>'
    assert discover_livepocket_event_urls(html, source.discovery_urls[0], source, config) == []
    html = (FIXTURES / "index.html").read_text().replace(
        "ONE PIECEカードゲーム ブースターパック 神の支配【OP-18】1BOX購入権",
        "ONE PIECEカードゲーム スタートデッキ",
    )
    assert discover_livepocket_event_urls(html, source.discovery_urls[0], source, config) == []


def test_wrong_official_store_is_rejected():
    config, source = settings()
    html = (FIXTURES / "event.html").read_text().replace("涌谷", "別店舗")
    with pytest.raises(ValueError):
        parse_livepocket_event(html, EVENT, source, config)


def test_pipeline_fetches_current_and_next_event_urls():
    config, source = settings()
    config = replace(config, sources=[source])
    next_event = EVENT + "-next"

    class Fetcher:
        def fetch(self, url, etag=None, last_modified=None):
            if url == source.discovery_urls[0]:
                html = (FIXTURES / "index.html").read_text().replace(EVENT, next_event)
            else:
                assert url == next_event
                html = (FIXTURES / "event.html").read_text()
            return FetchResult(url, 200, html, {})

    cases, _, alerts = run_pipeline(config, http_fetcher=Fetcher())
    assert not alerts
    assert len(cases) == 1
    assert cases[0].official_url == next_event


class IndexFallbackFetcher:
    def __init__(self, official_status=202, detail=None, extra_event=False):
        self.official_status = official_status
        self.detail = detail or (FIXTURES / "index_detail.html").read_text()
        self.extra_event = extra_event
        self.calls = []

    def fetch(self, url, etag=None, last_modified=None):
        self.calls.append(url)
        if "/store/" in url:
            html = (FIXTURES / "index.html").read_text()
            if self.extra_event:
                # 同じ索引の別抽選。詳細の補完先がない失敗まで隠してはいけない。
                html = html.replace("</ul>", '<li>ONE PIECEカードゲーム '
                    'ブースターパック 神の支配【OP-18】1BOX購入権 '
                    f'<a href="{EVENT}-next">応募ページ</a></li></ul>')
            return FetchResult(url, 200, html, {})
        if "tcg-chusen.com/l/" in url:
            return FetchResult(url, 200, self.detail, {})
        if self.official_status == 200:
            return FetchResult(url, 200, (FIXTURES / "event.html").read_text(), {})
        return FetchResult(url, self.official_status, "<h1>checking your browser</h1>", {})


@freeze_time("2026-11-10T03:00:00Z")
def test_official_challenge_uses_existing_index_detail_and_preserves_raw_failure(tmp_path):
    config, source = settings()
    config = replace(config, sources=[source])
    state = MonitorState.load(tmp_path / "state.json")
    fetcher = IndexFallbackFetcher()
    cases, _, alerts = run_pipeline(config, monitor_state=state, http_fetcher=fetcher)
    assert not alerts and len(cases) == 1
    case = cases[0]
    assert case.start_at.isoformat() == "2026-11-07T12:00:00+09:00"
    assert case.end_at.isoformat() == "2026-11-10T21:00:00+09:00"
    assert case.confidence == "medium" and case.source_tier.value == "secondary"
    assert case.official_url == EVENT
    assert case.source_url == "https://tcg-chusen.com/l/e247aae3bf/"
    record = state.data["monitors"][source.id]
    assert record["outcome"] == "degraded"
    assert record["http_status"] == 202 and record["failure_cause"] == "challenge"
    assert record["consecutive_failures"] == 1
    assert record["routes"][EVENT]["status"] == "fetch_failed"
    assert state.data["last_run_summary"]["degraded_monitors"] == 1
    state.mark_delivered("lottery:started:" + case.case_id)

    # 同じ抽選の再巡回・公式復旧でDiscord/予定の識別が変わらない。
    repeated, _, _ = run_pipeline(config, monitor_state=state,
                                  http_fetcher=IndexFallbackFetcher())
    assert repeated[0].case_id == case.case_id
    assert state.delivered("lottery:started:" + repeated[0].case_id)
    restored_fetcher = IndexFallbackFetcher(official_status=200)
    restored, _, alerts = run_pipeline(config, monitor_state=state, http_fetcher=restored_fetcher)
    assert not alerts and restored[0].case_id == case.case_id
    assert state.delivered("lottery:started:" + restored[0].case_id)
    assert state.data["monitors"][source.id]["outcome"] == "success"
    assert case.source_url not in restored_fetcher.calls
    next_case = replace(case, official_url=EVENT + "-next").with_id()
    assert next_case.case_id != case.case_id


@pytest.mark.parametrize("before,after", [
    ("TSUTAYA 涌谷店", "TSUTAYA 別店舗"),
    (EVENT, EVENT + "-wrong"),
    ('data-start="2026-11-07T12:00:00+09:00"', ""),
    ("2026-11-07T12:00:00+09:00", "2026-11-07T12:00:00"),
    ("2026-11-07T12:00:00+09:00", "2026-11-12T12:00:00+09:00"),
    ("OP-18", "OP-19"),
])
@freeze_time("2026-11-10T03:00:00Z")
def test_invalid_index_detail_keeps_alert_and_does_not_create_candidate(tmp_path, before, after):
    config, source = settings()
    detail = (FIXTURES / "index_detail.html").read_text().replace(before, after)
    cases, _, alerts = run_pipeline(replace(config, sources=[source]),
        monitor_state=MonitorState.load(tmp_path / "state.json"),
        http_fetcher=IndexFallbackFetcher(detail=detail))
    assert not cases and alerts


@freeze_time("2026-11-10T03:00:00Z")
def test_partial_fallback_keeps_unread_second_event_alert(tmp_path):
    config, source = settings()
    state = MonitorState.load(tmp_path / "state.json")
    cases, _, alerts = run_pipeline(replace(config, sources=[source]), monitor_state=state,
        http_fetcher=IndexFallbackFetcher(extra_event=True))
    assert len(cases) == 1 and alerts
    assert state.data["monitors"][source.id]["outcome"] == "failed"


@freeze_time("2026-11-10T12:01:00Z")
def test_expired_index_detail_does_not_notify(tmp_path):
    config, source = settings()
    cases, _, alerts = run_pipeline(replace(config, sources=[source]),
        monitor_state=MonitorState.load(tmp_path / "state.json"),
        http_fetcher=IndexFallbackFetcher())
    assert not cases and alerts
