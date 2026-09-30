from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from tcg_monitor.config import load_config
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime

NOTICE = """ヤマダデンキ（アプリ）にてワンピースカード
「Heroines Edition vol.2【EB-05】」抽選！
📅応募期間：9/29 23時〜10/1まで
🎯当選発表：10/28 12時頃
アプリTOP→「店頭セール」内バナーから応募"""


def _parse(text: str, detected: date = date(2026, 9, 30)):
    config = load_config("sites.yaml")
    source = next(
        item for item in config.sources
        if item.id == "yahoo_realtime_yamada_onepiece_secondary"
    )
    html = f"""<div class="Tweet_TweetContainer__test">
    <p class="Tweet_body__test">{text}</p>
    <time><a href="https://x.com/premier777aa/status/2104972501919158561">
    9月29日</a></time></div>"""
    return parse_yahoo_realtime(html, source.discovery_urls[0], source, config, detected)


def test_yamada_eb05_real_notice_keeps_opening_and_result_times() -> None:
    cases, releases, alerts = _parse(NOTICE)
    assert not releases
    assert not alerts
    assert len(cases) == 1
    case = cases[0]
    assert case.retailer_id == "yamada_denki"
    assert case.product_name == "Heroines Edition vol.2【EB-05】"
    assert case.canonical_product_key == "EB-05"
    assert case.start_at == datetime(2026, 9, 29, 23, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert case.end_at == date(2026, 10, 1)
    assert case.result_at == datetime(2026, 10, 28, 12, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert case.confidence == "medium"


@pytest.mark.parametrize("text", [
    NOTICE.replace("ヤマダデンキ", "他の店舗"),
    "ヤマダデンキ ワンピースカード EB-05 抽選結果発表！"
    "販売期間：10/31 10時〜11/6まで",
    "ヤマダデンキ ワンピースカード EB-05 抽選！応募期間：10/1まで",
])
def test_yamada_unrelated_result_and_deadline_only_posts_are_not_openings(text: str) -> None:
    cases, _, alerts = _parse(text)
    assert not cases
    assert not alerts


def test_yamada_closed_application_is_not_announced_again() -> None:
    cases, _, alerts = _parse(NOTICE, date(2026, 10, 2))
    assert not cases
    assert not alerts


def test_yamada_application_sources_are_enabled_with_empty_search_fallback() -> None:
    config = load_config("sites.yaml")
    for source_id in (
        "yahoo_realtime_yamada_secondary",
        "yahoo_realtime_yamada_onepiece_secondary",
    ):
        source = next(item for item in config.sources if item.id == source_id)
        assert source.enabled
        assert source.fallback_on_empty_result
        assert len(source.discovery_urls) >= 2
