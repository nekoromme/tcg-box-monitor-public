"""10月10日の実配信と、途中で省略された公式告知からの回帰確認。"""
import json
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock

from tcg_monitor.cli import _prepare_cases, _remember_case
from tcg_monitor.config import load_config
from tcg_monitor.fxembed import post_markup
from tcg_monitor.lottery_state_repair import repair
from tcg_monitor.models import LotteryCase, OpportunityKind, SourceTier
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = load_config("sites.yaml")
SOURCE = next(s for s in CONFIG.sources if s.id == "yahoo_realtime_fullcomp_sendai")


def fixture() -> dict:
    return json.loads((FIXTURES / "duplicate_notifications_20261010.json").read_text())


def case(record: dict) -> LotteryCase:
    fields = dict(record)
    for key in ("start_at", "end_at", "result_at"):
        value = fields.get(key)
        if value:
            fields[key] = (datetime.fromisoformat(value) if len(value) > 10
                           else date.fromisoformat(value))
    fields["source_tier"] = SourceTier(fields["source_tier"])
    fields["opportunity_kind"] = OpportunityKind(fields["opportunity_kind"])
    return LotteryCase(**fields)


def parsed_fullcomp() -> list[LotteryCase]:
    saved = fixture()
    raw = json.loads((FIXTURES / "fullcomp_public_post_20261010.json").read_text())
    markup = post_markup(raw, "fc_sendaieki")
    assert markup is not None
    candidates = []
    for html in (
        (FIXTURES / "fullcomp_truncated_deadline_20261010.html").read_text(), markup,
    ):
        cases, _, alerts = parse_yahoo_realtime(
            html, SOURCE.discovery_urls[0], SOURCE, CONFIG,
            detected_on=date(2026, 10, 10), ocr_cache=deepcopy(saved["ocr_cache"]),
        )
        assert not alerts
        assert len(cases) == 1
        assert cases[0].end_at == datetime.fromisoformat("2026-10-12T23:59:00+09:00")
        candidates.extend(cases)
    return candidates


def test_real_truncated_yahoo_and_complete_public_post_make_one_correct_lottery():
    merged, alerts = merge_lotteries(parsed_fullcomp())
    assert not alerts
    assert len(merged) == 1
    assert merged[0].official_url == "https://livepocket.jp/e/birt9"


def test_actual_start_keeps_priority_over_resolved_link_with_unknown_start():
    candidates = parsed_fullcomp()
    actual = replace(candidates[0], start_at=date(2026, 10, 10),
                     extraction_method="yahoo_realtime_body_application_period")
    merged, _ = merge_lotteries([candidates[1], actual])
    assert len(merged) == 1
    assert merged[0].start_at == date(2026, 10, 10)
    assert merged[0].extraction_method == actual.extraction_method


def test_real_morioka_reposts_keep_one_delivery_before_and_after_restart(tmp_path):
    saved = fixture()
    rows = [case(row) for row in saved["seen_cases"].values()
            if row["retailer_id"] == "batoloco_morioka"]
    assert len(rows) == 3
    state = MonitorState(tmp_path / "state.json")
    state.data.update(saved)
    # 本番の旧版では、履歴移行後にこの3件すべてを配信候補へ戻していた。
    prepared, count = _prepare_cases(state, rows)
    assert count == 0
    assert len(prepared) == 1
    initial = prepared[0]
    assert initial.start_at == date(2026, 10, 9)
    assert state.delivered(f"lottery:started:{initial.case_id}")
    assert state.data["calendar_sync"][f"lottery:{initial.case_id}"]["event_id"] == (
        "tcg4befc5d23f36fd14fc5ffc55ec5db4d92e73f7af639621869b1d4256c742f"
    )
    _remember_case(state, initial)
    state.save()
    for day in (11, 12, 13):
        state = MonitorState.load(state.path)
        reposts = [replace(row, start_at=date(2026, 10, day)) for row in rows]
        replay, count = _prepare_cases(state, reposts)
        assert count == 0
        assert len(replay) == 1
        assert replay[0].case_id == initial.case_id
        assert replay[0].start_at == initial.start_at
        assert state.delivered(f"lottery:started:{replay[0].case_id}")
        _remember_case(state, replay[0])
        state.save()


def test_verified_fullcomp_deadline_repair_keeps_delivery_and_queues_extra_event(tmp_path):
    saved = fixture()
    # 元投稿本文・添付画像の両方で12日23:59と確認できた履歴だけを補正する。
    # 次回募集を推測で統合しないため、一般の履歴にこの補正は適用しない。
    for row in saved["seen_cases"].values():
        if row["source_url"].endswith("/2108806066981282193"):
            row["end_at"] = "2026-10-12T23:59:00+09:00"
    state = MonitorState(tmp_path / "state.json")
    state.data.update(saved)
    prepared, count = _prepare_cases(state, parsed_fullcomp())
    assert count == 0
    assert len(prepared) == 1
    kept = prepared[0]
    assert state.delivered(f"lottery:started:{kept.case_id}")
    assert state.data["calendar_sync"][f"lottery:{kept.case_id}"]["event_id"] == (
        "tcg844418888fe36ab3746f79f2cc8b807d38cb5579207fd1abdb9b4fbbc1d62"
    )
    pending = state.data["case_id_migrations"][kept.case_id]["duplicate_calendar_events"]
    assert len(pending) == 1
    assert next(iter(pending)) == (
        "tcg3dbb832ad11c87136b2aecad72186df502eacaf64394e4dc3c292f25768ee"
    )


def test_new_deadline_store_product_round_and_application_remain_separate():
    rows = [case(row) for row in fixture()["seen_cases"].values()
            if row["retailer_id"] == "batoloco_morioka"]
    initial = rows[0]
    for change in (
        {"retailer_id": "batoloco_sendai"},
        {"official_url": "https://t.co/another-form"},
        {"canonical_product_key": "30th", "product_name": "30th CELEBRATION BOX"},
        {"application_round": "second"},
    ):
        assert len(merge_lotteries([initial, replace(initial, **change)])[0]) == 2
    first = replace(initial, end_at=date(2026, 10, 14))
    second = replace(first, end_at=date(2026, 11, 14))
    assert len(merge_lotteries([first, second])[0]) == 2


def test_production_repair_migrates_actual_state_once_without_notifications(tmp_path):
    state = MonitorState(tmp_path / "state.json")
    state.data.update(fixture())
    calendar = Mock()
    calendar.reconcile.side_effect = lambda *args, **kwargs: {
        "status": "unchanged", "event_id": kwargs["known_event_id"],
    }
    calendar.delete_owned_event.return_value = {"status": "deleted"}
    assert repair(state, calendar, CONFIG) == 2
    calendar.delete_owned_event.assert_called_once_with(
        "tcg3dbb832ad11c87136b2aecad72186df502eacaf64394e4dc3c292f25768ee",
        kind="lottery", internal_id=(
            "6f1e93c0b350a0bc5375fcb4b2744b049808538fb175e8044aa1cb75022defb4"
        ),
    )
    assert len(state.data["seen_cases"]) == 2
    restored = MonitorState.load(state.path)
    calendar.reset_mock()
    assert repair(restored, calendar, CONFIG) == 0
    calendar.reconcile.assert_not_called()
    calendar.delete_owned_event.assert_not_called()
