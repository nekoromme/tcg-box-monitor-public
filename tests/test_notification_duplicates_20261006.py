"""実際のホビステ二重通知と、同時に届いた入荷Nowの解析異常を再現する。"""
import json
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from tcg_monitor.cli import _prepare_cases, _remember_case
from tcg_monitor.config import load_config
from tcg_monitor.identity import release_title_token
from tcg_monitor.models import LotteryCase, OpportunityKind, SourceTier
from tcg_monitor.parsers.local_lottery import parse_hobby_station_news
from tcg_monitor.parsers.premium_bandai import parse_nyuka_now_lottery_summary
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = load_config("sites.yaml")


def _real_cases() -> list[LotteryCase]:
    records = json.loads(
        (FIXTURES / "hobby_station_duplicate_state_20261006.json").read_text()
    )["seen_cases"]
    return [LotteryCase(**{
        **row,
        "start_at": (datetime.fromisoformat(row["start_at"]) if len(row["start_at"]) > 10
                     else date.fromisoformat(row["start_at"])),
        "source_tier": SourceTier(row["source_tier"]),
        "opportunity_kind": OpportunityKind(row["opportunity_kind"]),
    }) for row in records.values()]


def test_actual_hobby_station_duplicates_merge_keep_history_and_restart(tmp_path: Path) -> None:
    fixture = json.loads(
        (FIXTURES / "hobby_station_duplicate_state_20261006.json").read_text()
    )
    state = MonitorState(tmp_path / "state.json")
    state.data.update(fixture)
    cases, alerts = merge_lotteries(_real_cases())
    assert len(cases) == 2
    assert not alerts
    assert all(case.source_tier == SourceTier.OFFICIAL for case in cases)
    prepared, count = _prepare_cases(state, cases)
    assert count == 0
    assert len(state.data["seen_cases"]) == 2
    for case in prepared:
        _remember_case(state, case)
        assert state.delivered(f"lottery:started:{case.case_id}")
        old_ids = {row.case_id for row in _real_cases()
                   if row.start_at.isoformat()[:10] == case.start_at.isoformat()[:10]}
        assert state.calendar_case_identity(case.case_id) in old_ids
    state.save()
    restored = MonitorState.load(state.path)
    # 公式サイトが一時的に取得できず、Xだけを再取得しても通知履歴を引き継ぐ。
    x_cases = [case for case in _real_cases() if case.source_tier == SourceTier.OFFICIAL_INDIRECT]
    replay, count = _prepare_cases(restored, merge_lotteries(x_cases)[0])
    assert count == 0
    assert all(restored.delivered(f"lottery:started:{case.case_id}") for case in replay)
    assert len(restored.data["seen_cases"]) == 2


@pytest.mark.parametrize("change", [
    {"start_at": date(2026, 10, 20)},
    {"retailer_id": "another_store"},
    {"product_name": "ポケモンカードゲームMEGA 拡張パック メガブレイブ",
     "canonical_product_key": "メガブレイブ"},
])
def test_real_next_campaign_store_and_product_still_notify(tmp_path: Path, change: dict) -> None:
    current = next(case for case in _real_cases()
                   if case.official_url == "https://livepocket.jp/e/cp5ds")
    state = MonitorState(tmp_path / "state.json")
    _prepare_cases(state, [current])
    _remember_case(state, current)
    state.mark_delivered(f"lottery:started:{current.case_id}")
    new = replace(current, **change,
                  official_url="https://livepocket.jp/e/new-round", case_id="").with_id()
    assert len(merge_lotteries([current, new])[0]) == 2
    _, count = _prepare_cases(state, [new])
    assert count == 1
    assert not state.delivered(f"lottery:started:{new.case_id}")


def test_actual_hobby_station_news_and_x_are_one_campaign() -> None:
    source = next(s for s in CONFIG.sources if s.id == "livepocket_hobby_station")
    cases, _, alerts = parse_hobby_station_news(
        (FIXTURES / "hobby_station_storm_20261006.html").read_text(),
        source.discovery_urls[0], source, CONFIG,
    )
    x_case = next(case for case in _real_cases()
                  if case.product_name.endswith("ストームエメラルダ"))
    assert not alerts
    merged, _ = merge_lotteries([*cases, x_case])
    assert len(merged) == 1
    assert merged[0].official_url == "https://livepocket.jp/e/cp5ds"


@pytest.mark.parametrize("prefix", [
    "ポケモンカードゲームMEGA", "MEGA", "ポケモンカードゲーム スカーレット＆バイオレット",
])
def test_series_prefix_is_removed_only_before_pack_category(prefix: str) -> None:
    assert release_title_token(prefix + " 拡張パック ストームエメラルダ") == "ストームエメラルダ"
    assert release_title_token("ポケモンカードゲーム ハイクラスパック MEGA DREAM ex") == (
        "megadreamex"
    )


def test_actual_aeon_and_premium_bandai_spacing_recovers_both_products() -> None:
    source = next(s for s in CONFIG.sources if s.id == "nyuka_now_fullcomp_livepocket")
    cases, _, alerts = parse_nyuka_now_lottery_summary(
        (FIXTURES / "nyuka_game_spacing_20261006.html").read_text(),
        "https://nyuka-now.com/archives/97393", source, CONFIG,
    )
    assert not alerts
    assert len(cases) == 2
    assert {(case.retailer_id, case.canonical_product_key) for case in cases} == {
        ("aeon_style_online", "EB-05"),
        ("premium_bandai", "nonbox:onepiece_anniversary_set:4thanniversaryset"),
    }
    assert {case.start_at.isoformat()[:10] for case in cases} == {"2026-10-07", "2026-10-14"}


@pytest.mark.parametrize("name", ["ONE PIECE カードゲーム", "ONEPIECEカードゲーム"])
def test_same_spacing_in_fullcomp_summary_is_also_recognized(name: str) -> None:
    source = next(s for s in CONFIG.sources if s.id == "nyuka_now_fullcomp_livepocket")
    html = f"""
      <h2>抽選・予約応募受付中のストア</h2><h3>フルコンプ仙台店</h3>
      <table><tr><th>対象商品</th><td>{name} ブースターパック 世界最強の戦士【OP-17】</td></tr>
      <tr><th>開始日</th><td>10月6日(火)12:00</td></tr>
      <tr><th>応募店舗</th><td>仙台</td></tr>
      <tr><th>応募ページ</th><td><a href="https://livepocket.jp/e/abcde">応募</a></td></tr>
      </table>
    """
    cases, _, alerts = parse_nyuka_now_lottery_summary(
        html, "https://nyuka-now.com/archives/97393", source, CONFIG,
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].canonical_product_key == "OP-17"


@pytest.mark.parametrize("reverse", [False, True])
def test_news_index_keeps_past_draws_from_consuming_current_delivery(
    tmp_path: Path, reverse: bool,
) -> None:
    fixture = json.loads((FIXTURES / "hobby_station_all_history_20261006.json").read_text())
    state = MonitorState(tmp_path / "state.json")
    state.data.update(fixture)
    source = next(s for s in CONFIG.sources if s.id == "livepocket_hobby_station")
    official, _, alerts = parse_hobby_station_news(
        (FIXTURES / "hobby_station_news_history_20261006.html").read_text(),
        source.discovery_urls[0], source, CONFIG,
    )
    assert not alerts
    x_cases = [case for case in _real_cases() if case.source_tier == SourceTier.OFFICIAL_INDIRECT]
    merged, _ = merge_lotteries([*official, *x_cases])
    if reverse:
        merged.reverse()
    prepared, count = _prepare_cases(state, merged)
    assert count == 0
    storm = [case for case in prepared if "ストームエメラルダ" in case.product_name]
    assert {case.start_at.isoformat()[:10] for case in storm} == {
        "2026-09-01", "2026-09-18", "2026-10-06",
    }
    current = next(case for case in storm if case.start_at.isoformat()[:10] == "2026-10-06")
    assert state.delivered(f"lottery:started:{current.case_id}")
    for case in prepared:
        _remember_case(state, case)
    state.save()
    restored = MonitorState.load(state.path)
    replay, count = _prepare_cases(restored, merged)
    assert count == 0
    current = next(case for case in replay if case.case_id == current.case_id)
    assert restored.delivered(f"lottery:started:{current.case_id}")


@pytest.mark.parametrize("reverse", [False, True])
def test_old_x_post_detected_today_is_merged_before_history_moves(
    tmp_path: Path, reverse: bool,
) -> None:
    state = MonitorState(tmp_path / "state.json")
    state.data.update(json.loads(
        (FIXTURES / "hobby_station_all_history_20261006.json").read_text()
    ))
    official = [case for case in _real_cases() if case.source_tier == SourceTier.OFFICIAL]
    x_cases = [replace(case, start_at=date(2026, 10, 6)) for case in _real_cases()
               if case.source_tier == SourceTier.OFFICIAL_INDIRECT]
    candidates, _ = merge_lotteries([*official, *x_cases])
    assert len(candidates) == 3  # 10月2日の投稿の仮日付は今日にずれている。
    if reverse:
        candidates.reverse()
    prepared, count = _prepare_cases(state, candidates)
    assert len(prepared) == 2
    assert count == 0
    assert all(case.source_tier == SourceTier.OFFICIAL for case in prepared)
    assert all(state.delivered(f"lottery:started:{case.case_id}") for case in prepared)
    assert len([row for row in state.data["seen_cases"].values()
                if row["start_at"][:10] in {"2026-10-02", "2026-10-06"}]) == 2
    for case in prepared:
        _remember_case(state, case)
    state.save()
    restored = MonitorState.load(state.path)
    later = [*official, *[replace(case, start_at=date(2026, 10, 7)) for case in x_cases]]
    replay, count = _prepare_cases(restored, merge_lotteries(later)[0])
    assert len(replay) == 2
    assert count == 0
    assert all(restored.delivered(f"lottery:started:{case.case_id}") for case in replay)
