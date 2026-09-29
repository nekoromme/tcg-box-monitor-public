from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from tcg_monitor.config import load_config
from tcg_monitor.parsers.aeon_style import parse_aeon_entry, parse_aeon_summary

URL = "https://aeonretail.com/Page/k-entry_01.aspx"
SUMMARY = Path("tests/fixtures/aeon_entry_summary.html").read_text()
TITLES = [
    "ドラゴンボールスーパーカードゲーム フュージョンワールド "
    "ブースターパック DUAL EVOLUTION[FB09] 24パックセット",
    "ドラゴンボールスーパーカードゲーム フュージョンワールド "
    "ブースターパック CROSS FORCE [FB10] 24パックセット",
    "ポケモンカードゲーム MEGA 拡張パック ストームエメラルダ 30パックセット",
    "ワンピース ONE PIECEカードゲーム ブースターパック 世界最強の戦士【OP-17】24パックセット",
]
# Synthetic HTML using the official page's verified product headings and periods.
OFFICIAL = "<h1>エントリー販売</h1>" + "".join(
    f"<h2>{name}</h2><div>本体価格4800円</div><div>エントリー期間 "
    "2026年9月28日(月)11:00～10月8日(木)23:59</div>"
    for name in TITLES
)


def source(source_id):
    config = load_config("sites.yaml")
    return config, next(s for s in config.sources if s.id == source_id)


@freeze_time("2026-09-29 00:00:00+00:00")
def test_four_products_match_official_and_live_summary_fixture():
    config, official = source("aeon_style_online")
    _, secondary = source("aeon_entry_summary")
    cases, _, alerts = parse_aeon_entry(OFFICIAL, URL, official, config)
    other, _, other_alerts = parse_aeon_summary(
        SUMMARY, secondary.discovery_urls[0], secondary, config
    )
    assert len(cases) == len(other) == 4
    assert not alerts and not other_alerts
    assert {c.case_id for c in cases} == {c.case_id for c in other}
    for c in cases + other:
        assert c.start_at == datetime(2026, 9, 28, 11, tzinfo=ZoneInfo("Asia/Tokyo"))
        assert c.end_at == datetime(2026, 10, 8, 23, 59, tzinfo=ZoneInfo("Asia/Tokyo"))
        assert c.official_url == URL
        assert c.result_at is None
    assert all(c.confidence == "medium" for c in other)


@freeze_time("2026-10-09 00:00:00+09:00")
def test_expired_campaign_is_not_replayed():
    config, official = source("aeon_style_online")
    _, secondary = source("aeon_entry_summary")
    assert not parse_aeon_entry(OFFICIAL, URL, official, config)[0]
    assert not parse_aeon_summary(SUMMARY, secondary.discovery_urls[0], secondary, config)[0]


@freeze_time("2026-09-29 00:00:00+00:00")
def test_neighbor_dates_and_unrelated_products_cannot_leak():
    config, secondary = source("aeon_entry_summary")
    html = '<h3>ゲオ</h3><table><tr><td>受付</td><td>9/1～9/2</td></tr></table>'
    html += SUMMARY + '<h3>他店</h3><p>エントリー期間 9/1～9/2</p>'
    cases, _, _ = parse_aeon_summary(html, secondary.discovery_urls[0], secondary, config)
    assert len(cases) == 4
    broken = SUMMARY.replace("9月28日(月)11:00", "")
    with pytest.raises(ValueError, match="period invalid"):
        parse_aeon_summary(broken, secondary.discovery_urls[0], secondary, config)
    with pytest.raises(ValueError, match="official link"):
        parse_aeon_summary(SUMMARY.replace("aeonretail.com", "example.com"), URL, secondary, config)


@freeze_time("2026-09-29 00:00:00+00:00")
def test_unknown_products_are_alerted_and_game_scope_is_respected():
    config, secondary = source("aeon_entry_summary")
    html = SUMMARY.replace("・CROSS FORCE", "・未知の新弾")
    cases, _, alerts = parse_aeon_summary(html, URL, secondary, config)
    assert len(cases) == 3
    assert any(a.reason_code == "aeon_entry_unknown_product" for a in alerts)
    only_pokemon = replace(secondary, supported_games={
        "pokemon_card": secondary.supported_games["pokemon_card"]
    })
    assert len(parse_aeon_summary(SUMMARY, URL, only_pokemon, config)[0]) == 1


@freeze_time("2026-09-29 00:00:00+00:00")
def test_official_dates_do_not_cross_product_boundaries():
    config, official = source("aeon_style_online")
    html = OFFICIAL.replace("2026年9月28日(月)11:00～10月8日(木)23:59", "後日案内", 1)
    cases, _, alerts = parse_aeon_entry(html, URL, official, config)
    assert len(cases) == 3 and len(alerts) == 1
    with pytest.raises(ValueError, match="missing"):
        parse_aeon_entry("<title>アクセス確認</title>", URL, official, config)
