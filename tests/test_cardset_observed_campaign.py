"""ドラスタの実通知3件から、仮日付・再告知の重複と次回募集を検証する。"""
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from tcg_monitor.cli import _prepare_cases, _preserve_preferred_case_source
from tcg_monitor.models import LotteryCase, OpportunityKind, SourceTier
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState

FIXTURE = Path(__file__).parent / "fixtures/dragonstar_cardset_duplicate_state_20261006.json"


def _case(record: dict) -> LotteryCase:
    return LotteryCase(**{
        **record,
        "start_at": date.fromisoformat(record["start_at"]),
        "end_at": date.fromisoformat(record["end_at"]) if record.get("end_at") else None,
        "source_tier": SourceTier(record["source_tier"]),
        "opportunity_kind": OpportunityKind(record["opportunity_kind"]),
    })


def _real_cases() -> list[LotteryCase]:
    return [_case(record) for record in json.loads(FIXTURE.read_text())["seen_cases"].values()]


def test_real_three_deliveries_merge_and_survive_restart(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text())
    state = MonitorState(tmp_path / "state.json")
    state.data.update(fixture)
    merged, _ = merge_lotteries(_real_cases())
    assert len(merged) == 1
    prepared, new_count = _prepare_cases(state, merged)
    case = prepared[0]
    assert new_count == 0
    assert case.start_at == date(2026, 10, 5)
    assert state.delivered(f"lottery:started:{case.case_id}")
    assert len(state.data["seen_cases"]) == 1
    assert state.calendar_case_identity(case.case_id) == _real_cases()[0].case_id
    state.save()
    restored = MonitorState.load(state.path)
    later = replace(_real_cases()[-1], start_at=date(2026, 10, 8))
    later_merged, _ = merge_lotteries([later])
    prepared, new_count = _prepare_cases(restored, later_merged)
    assert new_count == 0
    assert prepared[0].case_id == case.case_id
    assert prepared[0].start_at == case.start_at
    assert restored.delivered(f"lottery:started:{case.case_id}")


def test_actual_start_discovered_later_does_not_repeat_notification(tmp_path: Path) -> None:
    first = _real_cases()[0]
    state = MonitorState(tmp_path / "state.json")
    state.data.update(json.loads(FIXTURE.read_text()))
    actual = replace(
        first, start_at=date(2026, 10, 4), confidence="medium",
        extraction_method="yahoo_realtime_image_ocr_application_period",
    )
    merged, _ = merge_lotteries([first, actual])
    assert len(merged) == 1
    assert merged[0].start_at == date(2026, 10, 4)
    prepared, count = _prepare_cases(state, merged)
    assert count == 0
    assert state.delivered(f"lottery:started:{prepared[0].case_id}")


@pytest.mark.parametrize("change", [
    {"end_at": date(2026, 10, 13)},
    {"retailer_id": "other_store"},
    {"application_round": "second"},
    {"canonical_product_key": "30th", "product_name": "30th CELEBRATION"},
])
def test_next_deadline_store_round_and_box_are_not_suppressed(
    tmp_path: Path, change: dict,
) -> None:
    first = replace(_real_cases()[0], application_round="first")
    initial = merge_lotteries([first])[0][0]
    state = MonitorState(tmp_path / "state.json")
    state.data["seen_cases"][initial.case_id] = {
        **initial.__dict__, "start_at": initial.start_at.isoformat(),
        "end_at": initial.end_at.isoformat(),
    }
    state.data["delivery_journal"][f"lottery:started:{initial.case_id}"] = {
        "status": "complete", "updated_at": "2026-10-04T14:27:56+00:00",
    }
    next_case = replace(first, **change).with_id()
    cases, _ = merge_lotteries([first, next_case])
    assert len(cases) == 2
    next_case = next(case for case in cases if case.case_id != initial.case_id)
    assert state.migrate_case_identity(next_case) is None
    assert not state.delivered(f"lottery:started:{next_case.case_id}")


def test_no_deadline_uses_post_identity_without_day_drift() -> None:
    first = replace(_real_cases()[0], end_at=None)
    later = replace(first, start_at=date(2026, 10, 8))
    assert merge_lotteries([first])[0][0].case_id == merge_lotteries([later])[0][0].case_id
    other_post = replace(first, source_url="https://x.com/ds_ecommerce/status/2107999999999999999",
                         official_url="https://x.com/ds_ecommerce/status/2107999999999999999")
    assert len(merge_lotteries([first, other_post])[0]) == 2


def test_next_actual_start_is_new_without_changing_existing_ids(tmp_path: Path) -> None:
    first = replace(_real_cases()[0], extraction_method="yahoo_realtime_body_application_period")
    initial = merge_lotteries([first])[0][0]
    state = MonitorState(tmp_path / "state.json")
    state.data["seen_cases"][initial.case_id] = {
        **initial.__dict__, "start_at": initial.start_at.isoformat(),
        "end_at": initial.end_at.isoformat(),
    }
    next_case = merge_lotteries([replace(first, start_at=date(2026, 11, 5))])[0][0]
    assert next_case.case_id != initial.case_id
    assert state.migrate_case_identity(next_case) is None


def test_same_deadline_keeps_previously_confirmed_official_source(tmp_path: Path) -> None:
    official = replace(_real_cases()[0], source_tier=SourceTier.OFFICIAL)
    official = merge_lotteries([official])[0][0]
    state = MonitorState(tmp_path / "state.json")
    state.data["seen_cases"][official.case_id] = {
        **official.__dict__, "start_at": official.start_at.isoformat(),
        "end_at": official.end_at.isoformat(),
    }
    secondary = replace(official, source_tier=SourceTier.SECONDARY,
                        source_url="https://example.com/summary", start_at=date(2026, 10, 7))
    preserved = _preserve_preferred_case_source(state, secondary)
    assert preserved.source_url == official.source_url
    assert preserved.start_at == official.start_at
