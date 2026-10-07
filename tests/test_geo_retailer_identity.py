from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time

from tcg_monitor.cli import _cleanup_confirmed_false_positive_cases
from tcg_monitor.config import load_config
from tcg_monitor.google_calendar import CalendarAdapter
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.parsers.snkrdunk import parse_snkrdunk
from tcg_monitor.retailer_identity import retailer_mention_matches
from tcg_monitor.state import MonitorState

CONFIG = load_config("sites.yaml")
SOURCE = next(s for s in CONFIG.sources if s.id == "snkrdunk_pokemon")
URL = "https://snkrdunk.com/articles/33304/"
CASE_ID = "51ab65736f47928b107768c5921d1833d07ae1b835e862f7649a0f8640a6f2de"
HTML = Path("tests/fixtures/snkrdunk_geo_sabae_20261007.html").read_text()


@pytest.mark.parametrize("name", [
    "SuperKaBoS+GEO 鯖江店", "SuperKaBoS GEO鯖江店", "SuperKaBoS＋ＧＥＯ鯖江店",
    "スーパーカボス＋ゲオ鯖江店", "GEO＋SuperKaBoS鯖江店", "GEO鯖江店",
    "GEO（全国）鯖江店", "unrelatedGEOshop", "文真堂書店ゲオ 倉賀野店",
])
@freeze_time("2026-10-07 20:00:00+09:00")
def test_other_store_heading_does_not_become_a_geo_campaign(name: str) -> None:
    html = HTML.replace("SuperKaBoS+GEO 鯖江店", name)
    cases, _, alerts = parse_snkrdunk(html, URL, SOURCE, CONFIG)
    assert not cases
    assert not alerts  # 対象外の店を「開始日時が読めない異常」にも変えない。


@pytest.mark.parametrize("name", ["ゲオ", "GEO", "ＧＥＯ", "ゲオ（GEO）", "GEO（全国）"])
@freeze_time("2026-10-07 20:00:00+09:00")
def test_national_geo_heading_and_application_are_still_recognized(name: str) -> None:
    html = HTML.replace("SuperKaBoS+GEO 鯖江店", name).replace(
        "https://x.com/cdsksabae/status/2107425650055233849?s=20&amp;slide=modal",
        "https://geo-online.co.jp/news/785",
    )
    cases, _, alerts = parse_snkrdunk(html, URL, SOURCE, CONFIG)
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "geo"
    assert cases[0].official_url == "https://geo-online.co.jp/news/785"


@pytest.mark.parametrize("name", [
    "SuperKaBoS+GEO鯖江店", "SuperKaBoS GEO鯖江店", "スーパーカボス＋ゲオ鯖江店",
    "文真堂書店ゲオ 倉賀野店",
])
@freeze_time("2026-10-07 20:00:00+09:00")
def test_secondary_feed_cannot_route_the_same_other_store_to_geo(name: str) -> None:
    source = next(s for s in CONFIG.sources if s.id == "secondary_pokeget_news")
    body = (f"{name} ポケモンカード 拡張パック「30th CELEBRATION」1BOX 抽選販売 "
            "応募期間：10月6日20:00～10月11日23:59")
    html = (f'<div class="Tweet_TweetContainer__test"><p>{body}</p>'
            '<a href="https://x.com/PokeGetInfoMain/status/2107638439290261717">投稿</a>'
            '</div>')
    diagnostics: dict[str, int] = {}
    cases, _, alerts = parse_yahoo_realtime(
        html, source.discovery_urls[0], source, CONFIG, date(2026, 10, 7),
        diagnostics=diagnostics,
    )
    assert not cases and not alerts
    assert diagnostics["retailer_not_configured"] == 1

    # 同じ本文の全国チェーン名だけは採用し、除外を広げすぎない。
    assert retailer_mention_matches("geo", body.replace(name, "ゲオ"), ["ゲオ", "GEO"])
    valid_cases, _, valid_alerts = parse_yahoo_realtime(
        html.replace(name, "ゲオ"), source.discovery_urls[0], source, CONFIG,
        date(2026, 10, 7),
    )
    assert len(valid_cases) == 1 and not valid_alerts
    assert valid_cases[0].retailer_id == "geo"


@pytest.mark.parametrize("case_id", [
    CASE_ID, "3c5a22f01b1184df175da22500654f144ffed8932afca104490347ff17aa9953",
])
def test_known_wrong_event_is_removed_once_without_touching_real_geo(
    tmp_path: Path, case_id: str,
) -> None:
    expected = CONFIG.system["runtime"]["confirmed_false_positive_cases"][case_id]
    state = MonitorState.load(tmp_path / "state.json")
    state.data["seen_cases"] = {case_id: dict(expected), "real_geo": {"retailer_id": "geo"}}
    state.data["calendar_sync"] = {
        f"lottery:{case_id}": {"event_id": expected["event_id"]},
        "lottery:real_geo": {"event_id": "keep-real-event"},
    }
    state.data["delivery_journal"] = {
        f"lottery:started:{case_id}": {"status": "complete"},
        "lottery:started:real_geo": {"status": "complete"},
    }
    calendar = MagicMock(spec=CalendarAdapter)
    calendar.delete_owned_event.return_value = {"status": "deleted"}
    records = {case_id: expected}
    assert _cleanup_confirmed_false_positive_cases(state, calendar, records)
    calendar.delete_owned_event.assert_called_once_with(
        expected["event_id"], kind="lottery", internal_id=case_id,
    )
    assert case_id not in state.data["seen_cases"]
    assert "real_geo" in state.data["seen_cases"]
    assert "lottery:real_geo" in state.data["calendar_sync"]
    assert "lottery:started:real_geo" in state.data["delivery_journal"]
    assert not _cleanup_confirmed_false_positive_cases(state, calendar, records)


def test_secondary_single_retailer_route_rejects_the_other_store() -> None:
    source = next(s for s in CONFIG.sources if s.id == "secondary_pokeget_news")
    options = dict(source.parser_options)
    options.pop("retailer_profiles")
    options.update(retailer_id="geo", retailer_name="ゲオ", required_retailer_mentions=["GEO"])
    scoped = replace(source, parser_options=options)
    html = ('<div class="Tweet_TweetContainer__test"><p>SuperKaBoS+GEO鯖江店 '
            'ポケモンカード 拡張パック「30th CELEBRATION」1BOX 抽選販売 '
            '応募期間：10月6日20:00～10月11日23:59</p>'
            '<a href="https://x.com/PokeGetInfoMain/status/2107638439290261717">投稿</a>'
            '</div>')
    assert not parse_yahoo_realtime(
        html, scoped.discovery_urls[0], scoped, CONFIG, date(2026, 10, 7),
    )[0]
