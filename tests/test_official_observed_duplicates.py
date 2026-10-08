"""ふるいち重複の再現用架空履歴と、他の開始日不明の取得経路を検証する。"""
import json
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from tcg_monitor.cli import (
    _lottery_description,
    _lottery_discord_description,
    _prepare_cases,
    _remember_case,
)
from tcg_monitor.identity import OBSERVED_START_METHODS
from tcg_monitor.models import LotteryCase, OpportunityKind, SourceTier
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState

FIXTURE = Path(__file__).parent / "fixtures/furuichi_synthetic_duplicate_state.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def _case(record: dict) -> LotteryCase:
    fields = dict(record)
    for key in ("start_at", "end_at", "result_at"):
        value = fields.get(key)
        if value:
            fields[key] = (datetime.fromisoformat(value) if len(value) > 10
                           else date.fromisoformat(value))
    fields["source_tier"] = SourceTier(fields["source_tier"])
    fields["opportunity_kind"] = OpportunityKind(fields["opportunity_kind"])
    return LotteryCase(**fields)


def _cases() -> list[LotteryCase]:
    return [_case(record) for record in _fixture()["seen_cases"].values()]


def test_furuichi_duplicates_keep_first_delivery_and_calendar_after_restart(tmp_path):
    state = MonitorState(tmp_path / "state.json")
    state.data.update(_fixture())
    merged, _ = merge_lotteries(_cases())
    assert len(merged) == 1
    prepared, count = _prepare_cases(state, merged)
    case = prepared[0]
    assert count == 0
    assert case.start_at == date(2026, 10, 7)
    assert state.delivered(f"lottery:started:{case.case_id}")
    assert len(state.data["seen_cases"]) == 1
    migration = state.data["case_id_migrations"][case.case_id]
    first_id = "a" * 64
    assert state.calendar_case_identity(case.case_id) == first_id
    assert len(migration["legacy_deliveries"]) == 2
    assert len(migration["duplicate_calendar_events"]) == 1
    _remember_case(state, case)
    state.save()
    restored = MonitorState.load(state.path)
    for day in (8, 9, 10, 11):
        candidate = replace(_cases()[0], start_at=date(2026, 10, day))
        prepared, count = _prepare_cases(restored, merge_lotteries([candidate])[0])
        assert count == 0
        assert prepared[0].case_id == case.case_id
        assert prepared[0].start_at == case.start_at
        assert restored.delivered(f"lottery:started:{case.case_id}")
        _remember_case(restored, prepared[0])
        restored.save()
        restored = MonitorState.load(restored.path)


@pytest.mark.parametrize("method", sorted(OBSERVED_START_METHODS))
def test_all_first_detection_routes_have_stable_cardset_identity(method, tmp_path):
    first = replace(_cases()[0], extraction_method=method, start_at=date(2026, 10, 7))
    initial = merge_lotteries([first])[0][0]
    state = MonitorState(tmp_path / "state.json")
    _remember_case(state, initial)
    state.data["delivery_journal"][f"lottery:started:{initial.case_id}"] = {
        "status": "complete", "updated_at": "2026-10-07T00:00:00+09:00",
    }
    later = replace(first, start_at=date(2026, 10, 8))
    replay, count = _prepare_cases(state, merge_lotteries([later])[0])
    assert count == 0
    assert replay[0].case_id == initial.case_id
    assert state.delivered(f"lottery:started:{replay[0].case_id}")
    # 同じページでも締切が変わる次回募集は、新規のまま通す。
    next_round = replace(later, end_at=date(2026, 11, 11)).with_id()
    prepared, count = _prepare_cases(state, merge_lotteries([next_round])[0])
    assert count == 1
    assert not state.delivered(f"lottery:started:{prepared[0].case_id}")


@pytest.mark.parametrize("change", [
    {"end_at": date(2026, 11, 11)},
    {"retailer_id": "other_store"},
    {"application_round": "second"},
    {"canonical_product_key": "30th", "product_name": "30th CELEBRATION BOX"},
])
def test_other_campaigns_remain_new(change, tmp_path):
    state = MonitorState(tmp_path / "state.json")
    fixture = deepcopy(_fixture())
    for row in fixture["seen_cases"].values():
        row["application_round"] = "first"
    state.data.update(fixture)
    first = replace(_cases()[0], application_round="first")
    _prepare_cases(state, merge_lotteries([first])[0])
    different = replace(first, **change).with_id()
    prepared, count = _prepare_cases(state, merge_lotteries([different])[0])
    assert count == 1
    assert not state.delivered(f"lottery:started:{prepared[0].case_id}")


def test_confirmed_start_recovery_reuses_delivery(tmp_path):
    state = MonitorState(tmp_path / "state.json")
    state.data.update(_fixture())
    actual = replace(_cases()[0], start_at=date(2026, 10, 6),
                     extraction_method="furuichi_official_image_application_period")
    merged = merge_lotteries([_cases()[0], actual])[0]
    assert len(merged) == 1
    prepared, count = _prepare_cases(state, merged)
    assert count == 0
    assert prepared[0].start_at == date(2026, 10, 6)
    assert state.delivered(f"lottery:started:{prepared[0].case_id}")


def test_official_detection_date_is_not_presented_as_actual_start():
    case = _cases()[0]
    assert "受付を確認した日（開始日時不明）" in _lottery_discord_description(case)
    assert "受付開始日: 不明" in _lottery_description(case, datetime(2026, 10, 8))


@pytest.mark.parametrize("game,product,name", [
    ("pokemon_card", "30th", "30th CELEBRATION BOX"),
    ("one_piece_card", "OP-17", "ONE PIECE OP-17"),
    ("dragon_ball_fusion_world", "FB11", "BRIGHTNESS OF HOPE FB11"),
    ("yu_gi_oh", "original_artwork", "ORIGINAL ARTWORK COLLECTION"),
])
def test_other_products_preserve_first_detection_and_delivery(game, product, name, tmp_path):
    first = replace(_cases()[0], game_id=game, product_name=name,
                    canonical_product_key=product, start_at=date(2026, 10, 7)).with_id()
    state = MonitorState(tmp_path / "state.json")
    _remember_case(state, first)
    state.data["delivery_journal"][f"lottery:started:{first.case_id}"] = {
        "status": "complete", "updated_at": "2026-10-07T00:00:00+09:00",
    }
    later = replace(first, start_at=date(2026, 10, 8)).with_id()
    prepared, count = _prepare_cases(state, merge_lotteries([later])[0])
    assert count == 0
    assert prepared[0].start_at == first.start_at
    assert state.delivered(f"lottery:started:{prepared[0].case_id}")


def test_official_and_social_routes_share_one_deadline_campaign():
    official = _cases()[0]
    social = replace(official, start_at=date(2026, 10, 9),
                     source_tier=SourceTier.OFFICIAL_INDIRECT,
                     extraction_method="yahoo_realtime_detected_open",
                     source_url="https://x.com/furu1_head/status/2109999999999999999")
    merged = merge_lotteries([official, social])[0]
    assert len(merged) == 1
    assert merged[0].source_url == official.source_url
