"""実際のプレバン告知と、情報源の交代で通知・予定を増やさない確認。"""

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from tcg_monitor.cli import _prepare_cases, _remember_case
from tcg_monitor.config import load_config
from tcg_monitor.identity import lottery_dedupe_key
from tcg_monitor.models import LotteryCase, SourceTier
from tcg_monitor.parsers.local_lottery import _application_start, parse_yahoo_realtime
from tcg_monitor.parsers.premium_bandai import parse_nyuka_now_lottery_summary
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState

CONFIG = load_config("sites.yaml")
NYUKA_URL = "https://nyuka-now.com/archives/97393"
POST_URL = "https://x.com/ONEPIECE_tcg/status/2106715970639180105"
START = datetime(2026, 10, 5, 12, tzinfo=ZoneInfo("Asia/Tokyo"))


def _real_cases() -> tuple[LotteryCase, LotteryCase]:
    source = next(s for s in CONFIG.sources if s.id == "yahoo_realtime_onepiece_premium_bandai")
    assert source.enabled and source.parser_options["account"] == "ONEPIECE_tcg"
    official, _, alerts = parse_yahoo_realtime(
        Path("tests/fixtures/onepiece_official_pbandai_20261004.html").read_text(),
        source.discovery_urls[0], source, CONFIG, date(2026, 10, 5),
    )
    assert len(official) == 1 and not alerts
    source = next(s for s in CONFIG.sources if s.id == "nyuka_now_fullcomp_livepocket")
    cases, _, alerts = parse_nyuka_now_lottery_summary(
        Path("tests/fixtures/nyuka_references_20261005.html").read_text(),
        NYUKA_URL, source, CONFIG,
    )
    assert not alerts
    fallback = next(c for c in cases if c.retailer_id == "premium_bandai"
                    and c.start_at == START)
    return official[0], fallback


@freeze_time("2026-10-05 07:39:00+09:00")
def test_real_official_notice_replaces_the_reported_nyuka_case() -> None:
    official, fallback = _real_cases()
    assert official.start_at == START
    assert official.source_url == POST_URL
    assert official.confidence == "high"
    assert official.official_url == "https://p-bandai.jp/item/item-1000259109/"
    assert lottery_dedupe_key(official) == lottery_dedupe_key(fallback)
    assert merge_lotteries([fallback, official])[0] == [official]
    assert merge_lotteries([official, fallback])[0] == [official]


@freeze_time("2026-10-05 07:39:00+09:00")
def test_secondary_individual_notice_wins_regardless_of_collection_order() -> None:
    _, fallback = _real_cases()
    alternate = replace(fallback, source_url="https://x.com/onepiecenyuka/status/12345").with_id()
    assert merge_lotteries([fallback, alternate])[0] == [alternate]
    assert merge_lotteries([alternate, fallback])[0] == [alternate]
    # 代替が読めなかった抽選は捨てず、見落とし防止の補助として残す。
    assert merge_lotteries([fallback])[0] == [fallback]


@freeze_time("2026-10-05 07:39:00+09:00")
def test_source_upgrade_keeps_delivery_history_and_original_calendar_id(tmp_path: Path) -> None:
    official, fallback = _real_cases()
    # スクリーンショットの旧参照URLとIDのまま保存していた状態から移行する。
    fallback = replace(fallback, source_url=NYUKA_URL).with_id()
    assert fallback.case_id == "a9cc3ff112d4cff0dd0c57a39272c95613fe24c7f5ffeafc4e64cf26f4d197be"
    state = MonitorState.load(tmp_path / "state.json")
    _remember_case(state, fallback)
    state.mark_delivered("lottery:started:" + fallback.case_id)
    state.data["calendar_sync"]["lottery:" + fallback.case_id] = {"event_id": "original"}
    prepared, new_count = _prepare_cases(state, [official])
    assert new_count == 0 and prepared[0].source_url == POST_URL
    assert state.delivered("lottery:started:" + official.case_id)
    assert state.calendar_case_identity(official.case_id) == fallback.case_id
    assert state.data["calendar_sync"]["lottery:" + official.case_id]["event_id"] == "original"
    _remember_case(state, prepared[0])
    # 翌巡回に公式が読めなくても、告知リンクと確定した時刻を下げない。
    lower = replace(fallback, start_at=date(2026, 10, 5))
    prepared, new_count = _prepare_cases(state, [lower])
    assert new_count == 0 and prepared[0].source_url == POST_URL
    assert prepared[0].start_at == START
    assert state.delivered("lottery:started:" + prepared[0].case_id)
    assert state.calendar_case_identity(prepared[0].case_id) == fallback.case_id


@freeze_time("2026-10-05 07:39:00+09:00")
def test_previous_reference_is_not_applied_to_a_different_round(tmp_path: Path) -> None:
    official, fallback = _real_cases()
    state = MonitorState.load(tmp_path / "state.json")
    old = replace(official, case_id=fallback.case_id)
    _remember_case(state, old)
    # 同じ保存IDがあっても、開始日が違う情報に過去の公式投稿は使わない。
    candidate = replace(fallback, start_at=date(2026, 11, 5))
    prepared, _ = _prepare_cases(state, [candidate])
    assert prepared[0].source_url == fallback.source_url


@freeze_time("2026-10-05 07:39:00+09:00")
def test_remaining_fallback_links_use_their_own_product_and_start_row() -> None:
    official, fallback = _real_cases()
    fragment = unquote(fallback.source_url.split("#:~:text=", 1)[1])
    assert "プレミアムカードコレクション" in fragment
    assert "2027年8月発送分" in fragment
    assert fragment.endswith(",10月5日(月)12:00")
    assert fallback.case_id == replace(fallback, source_url=NYUKA_URL).with_id().case_id
    source = next(s for s in CONFIG.sources if s.id == "nyuka_now_fullcomp_livepocket")
    cases, _, _ = parse_nyuka_now_lottery_summary(
        Path("tests/fixtures/nyuka_references_20261005.html").read_text(),
        NYUKA_URL, source, CONFIG,
    )
    aeon = next(c for c in cases if c.retailer_id == "aeon_style_online")
    # 別店舗の同じ商品の開始日を混ぜない。
    assert unquote(aeon.source_url).endswith(",9月28日(月)11:00")
    assert official.source_url == POST_URL


@pytest.mark.parametrize(("text", "expected"), [
    ("10月5日（月）12時よりプレミアムバンダイにて抽選販売を開始致します。", START),
    ("10/5(月)12:00から抽選応募を開始", START),
    ("10月4日発売。10月5日（月）12時より抽選販売を開始", START),
    ("10月5日（月）12時に当選発表。抽選販売の結果です。", None),
    ("10月5日（月）12時発売。抽選販売を開始します。", None),
])
def test_date_before_action_is_an_explicit_start_only(
    text: str, expected: datetime | None,
) -> None:
    assert _application_start(text, date(2026, 10, 4), include_sales_period=False) == expected


@freeze_time("2026-10-05 07:39:00+09:00")
def test_manufacturer_feed_does_not_turn_store_tournaments_into_pbandai_lotteries() -> None:
    source = next(s for s in CONFIG.sources if s.id == "yahoo_realtime_onepiece_premium_bandai")
    html = Path("tests/fixtures/onepiece_official_pbandai_20261004.html").read_text()
    html = html.replace("プレミアムバンダイ", "公式ショップ").replace("プレバン", "店舗")
    assert not parse_yahoo_realtime(html, source.discovery_urls[0], source, CONFIG)[0]
    assert source.source_tier == SourceTier.OFFICIAL_INDIRECT
