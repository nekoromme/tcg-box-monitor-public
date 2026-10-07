"""エディオンの実配信4回を再現し、翌日・旧履歴・別募集を確認する。"""
import json
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from tcg_monitor.cli import (
    _cleanup_duplicate_lottery_events,
    _lottery_discord_description,
    _prepare_cases,
    _remember_case,
)
from tcg_monitor.models import LotteryCase, OpportunityKind, SourceTier
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState

FIXTURE = Path(__file__).parent / "fixtures/edion_duplicate_state_20261007.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def _case(record: dict) -> LotteryCase:
    fields = dict(record)
    for key in ("start_at", "end_at", "result_at"):
        value = fields.get(key)
        if value:
            fields[key] = datetime.fromisoformat(value) if len(value) > 10 else date.fromisoformat(
                value,
            )
    fields["source_tier"] = SourceTier(fields["source_tier"])
    fields["opportunity_kind"] = OpportunityKind(fields["opportunity_kind"])
    return LotteryCase(**fields)


def _cases() -> list[LotteryCase]:
    return [_case(row) for row in _fixture()["seen_cases"].values()]


def test_real_daily_edion_notices_merge_restore_first_success_and_keep_calendar(
    tmp_path: Path,
) -> None:
    state = MonitorState(tmp_path / "state.json")
    state.data.update(_fixture())
    merged, _ = merge_lotteries(_cases())
    assert len(merged) == 1
    prepared, count = _prepare_cases(state, merged)
    case = prepared[0]
    assert count == 0
    assert case.start_at == date(2026, 10, 3)
    assert state.delivered(f"lottery:started:{case.case_id}")
    assert len(state.data["seen_cases"]) == 1
    assert state.calendar_case_identity(case.case_id) == _cases()[0].case_id
    sync = state.data["calendar_sync"][f"lottery:{case.case_id}"]
    assert sync["event_id"] == _fixture()["calendar_sync"][f"lottery:{_cases()[0].case_id}"][
        "event_id"
    ]
    pending = state.data["case_id_migrations"][case.case_id]["duplicate_calendar_events"]
    assert len(pending) == 3
    assert all(record["status"] == "pending" for record in pending.values())
    assert len(state.data["case_id_migrations"][case.case_id]["legacy_deliveries"]) == 4
    _remember_case(state, case)
    state.save()
    restored = MonitorState.load(state.path)
    for day in (7, 8, 9):
        later = replace(_cases()[-1], start_at=date(2026, 10, day))
        replay, count = _prepare_cases(restored, merge_lotteries([later])[0])
        assert count == 0
        assert replay[0].case_id == case.case_id
        assert replay[0].start_at == case.start_at
        assert restored.delivered(f"lottery:started:{case.case_id}")
        _remember_case(restored, replay[0])


@pytest.mark.parametrize("change", [
    {"source_url": "https://x.com/Trecapi_namba/status/2109999999999999999",
     "official_url": "https://edion-cp.com/poke110601"},
    {"retailer_id": "another_store"},
    {"application_round": "second"},
    {"canonical_product_key": "30th", "product_name": "30th CELEBRATION BOX"},
])
def test_another_post_store_round_and_box_are_new(tmp_path: Path, change: dict) -> None:
    state = MonitorState(tmp_path / "state.json")
    fixture = _fixture()
    current = _cases()
    if "application_round" in change:
        for row in fixture["seen_cases"].values():
            row["application_round"] = "first"
        current = [replace(case, application_round="first") for case in current]
    state.data.update(fixture)
    _prepare_cases(state, merge_lotteries(current)[0])
    new = replace(current[0], start_at=date(2026, 11, 6), **change).with_id()
    _, count = _prepare_cases(state, merge_lotteries([new])[0])
    assert count == 1


def test_start_recovered_from_same_post_keeps_notification_history(tmp_path: Path) -> None:
    state = MonitorState(tmp_path / "state.json")
    state.data.update(_fixture())
    actual = replace(_cases()[0], start_at=date(2026, 10, 2),
                     extraction_method="yahoo_realtime_body_application_period")
    prepared, count = _prepare_cases(state, merge_lotteries([actual])[0])
    assert count == 0
    assert prepared[0].start_at == date(2026, 10, 2)
    assert state.delivered(f"lottery:started:{prepared[0].case_id}")


def test_same_deadline_other_post_merges_but_next_deadline_does_not() -> None:
    first = replace(_cases()[0], end_at=date(2026, 10, 4))
    repeat = replace(first, source_url="https://x.com/Trecapi_namba/status/2106999999999999999",
                     start_at=date(2026, 10, 4))
    assert len(merge_lotteries([first, repeat])[0]) == 1
    later = replace(repeat, end_at=date(2026, 11, 8), start_at=date(2026, 11, 6))
    assert len(merge_lotteries([first, later])[0]) == 2


def test_first_detection_is_not_presented_as_confirmed_application_start() -> None:
    assert "受付を確認した日（開始日時不明）" in _lottery_discord_description(_cases()[0])


def test_duplicate_calendar_cleanup_verifies_survivor_and_resumes_after_failure(
    tmp_path: Path,
) -> None:
    state = MonitorState(tmp_path / "state.json")
    state.data.update(_fixture())
    case = _prepare_cases(state, merge_lotteries(_cases())[0])[0][0]
    kept = state.data["calendar_sync"][f"lottery:{case.case_id}"]["event_id"]
    calendar = Mock()
    calendar.reconcile.return_value = {"status": "unchanged", "event_id": kept}
    calendar.delete_owned_event.side_effect = [
        {"status": "deleted"}, RuntimeError("temporary outage"),
    ]
    with pytest.raises(RuntimeError, match="temporary outage"):
        _cleanup_duplicate_lottery_events(state, calendar, case, "same draw", "description")
    pending = state.data["case_id_migrations"][case.case_id]["duplicate_calendar_events"]
    assert sum(row["status"] == "deleted" for row in pending.values()) == 1
    snapshot = deepcopy(pending)
    restored = MonitorState.load(state.path)
    calendar.delete_owned_event.reset_mock(side_effect=True)
    calendar.delete_owned_event.return_value = {"status": "not_found"}
    _cleanup_duplicate_lottery_events(restored, calendar, case, "same draw", "description")
    assert calendar.delete_owned_event.call_count == 2
    assert all(call.args[0] != kept for call in calendar.delete_owned_event.call_args_list)
    for call in calendar.delete_owned_event.call_args_list:
        assert call.kwargs["internal_id"] == snapshot[call.args[0]]["internal_id"]
    calendar.delete_owned_event.reset_mock()
    _cleanup_duplicate_lottery_events(restored, calendar, case, "same draw", "description")
    calendar.delete_owned_event.assert_not_called()
