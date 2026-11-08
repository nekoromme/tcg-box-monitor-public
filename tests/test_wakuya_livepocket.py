from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tcg_monitor.config import load_config
from tcg_monitor.http_client import FetchResult
from tcg_monitor.parsers.local_lottery import (
    discover_livepocket_event_urls,
    parse_livepocket_event,
)
from tcg_monitor.pipeline import run_pipeline

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
