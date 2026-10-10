"""実例と同じ取得経路の違いを、公開してよい架空の履歴で再現する。"""
from dataclasses import replace
from datetime import date
from unittest.mock import Mock

import pytest

from tcg_monitor.cli import _prepare_cases, _remember_case
from tcg_monitor.config import load_config
from tcg_monitor.lottery_state_repair import _case, repair_social_route_duplicates
from tcg_monitor.models import LotteryCase, SourceTier
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState


def saved_state(tmp_path):
    # URL、送信日時、カレンダーIDは全て試験用。実運用の状態JSONを公開しない。
    state = MonitorState(tmp_path / "state.json")
    for index, retailer in enumerate(("seagull_common", "batoloco_morioka"), start=1):
        post = f"https://x.com/synthetic_store_{index}/status/{index}234567890123456789"
        linked = LotteryCase(
            game_id="pokemon_card", retailer_id=retailer, retailer_name="試験用店舗",
            product_name="30th CELEBRATION カードセット", product_category="カードセット",
            canonical_product_key="pokemon_30th_cardset", start_at=date(2026, 10, 9),
            official_url=f"https://t.co/SyntheticForm{index}", source_url=post,
            source_tier=SourceTier.OFFICIAL_INDIRECT,
            extraction_method="yahoo_realtime_detected_open", confidence="low",
        ).with_id()
        omitted = replace(linked, official_url=post)
        rows = [merge_lotteries([row])[0][0] for row in (linked, omitted)]
        for position, row in enumerate(rows):
            _remember_case(state, row)
            key = f"lottery:started:{row.case_id}"
            delivery = {"status": "complete", "updated_at": (
                "2026-10-10T12:00:00+00:00" if position == 0
                else "2026-10-09T00:00:00+00:00"
            )}
            state.data["delivery_journal"][key] = delivery
            state.data["calendar_sync"][f"lottery:{row.case_id}"] = {
                "status": "updated", "event_id": f"synthetic-calendar-{index}",
                "payload_hash": "synthetic-payload",
            }
            state.data["case_id_migrations"][row.case_id] = {
                "legacy_deliveries": {key: delivery}, "calendar_identity": rows[1].case_id,
            }
    return state


@pytest.mark.parametrize("retailer", ["seagull_common", "batoloco_morioka"])
@pytest.mark.parametrize("reverse", [False, True])
def test_same_post_routes_keep_one_delivery_across_restarts(tmp_path, retailer, reverse):
    state = saved_state(tmp_path)
    rows = [_case(row) for row in state.data["seen_cases"].values()
            if row["retailer_id"] == retailer
            and row["extraction_method"] == "yahoo_realtime_detected_open"]
    assert len(rows) == 2
    if reverse:
        rows.reverse()
    first_delivery = min(
        state.data["case_id_migrations"][row.case_id]["legacy_deliveries"][key]["updated_at"]
        for row in rows
        for key in state.data["case_id_migrations"][row.case_id]["legacy_deliveries"]
    )
    for day in (10, 11, 12):
        prepared, count = _prepare_cases(state, [replace(row, start_at=date(2026, 10, day))
                                                for row in rows])
        assert count == 0
        assert len(prepared) == 1
        current = prepared[0]
        assert current.official_url.startswith("https://t.co/")
        assert state.delivered(f"lottery:started:{current.case_id}")
        assert state.data["delivery_journal"][f"lottery:started:{current.case_id}"][
            "updated_at"
        ] == first_delivery
        assert current.start_at == date(2026, 10, 9)
        _remember_case(state, current)
        state.save()
        state = MonitorState.load(state.path)


def test_omitted_link_does_not_choose_between_two_forms_or_different_deadlines(tmp_path):
    state = saved_state(tmp_path)
    row = next(_case(row) for row in state.data["seen_cases"].values()
               if row["retailer_id"] == "batoloco_morioka"
               and row["official_url"].startswith("https://t.co/"))
    omitted = replace(row, official_url=row.source_url)
    other = replace(row, official_url="https://t.co/another-form")
    assert len(merge_lotteries([row, other, omitted])[0]) == 3
    first = replace(row, end_at=date(2026, 10, 14))
    second = replace(omitted, end_at=date(2026, 11, 14))
    assert len(merge_lotteries([first, second])[0]) == 2
    assert len(merge_lotteries([row, replace(omitted, application_round="second")])[0]) == 2


def test_migration_survivor_is_only_delivery_candidate_even_without_merge_alias(tmp_path):
    state = saved_state(tmp_path)
    row = next(_case(row) for row in state.data["seen_cases"].values()
               if row["retailer_id"] == "batoloco_morioka"
               and row["official_url"].startswith("https://t.co/"))
    # 同じ応募先が後から確定日付きで読めた場合も、履歴照合は一つの募集。
    confirmed = replace(row, extraction_method="yahoo_realtime_body_application_period").with_id()
    prepared, count = _prepare_cases(state, [row, confirmed])
    assert count == 0
    assert len(prepared) == 1
    assert state.delivered(f"lottery:started:{prepared[0].case_id}")


def test_existing_current_id_still_removes_an_earlier_prepared_alias(tmp_path):
    state = saved_state(tmp_path)
    row = next(_case(row) for row in state.data["seen_cases"].values()
               if row["retailer_id"] == "batoloco_morioka"
               and row["official_url"].startswith("https://t.co/"))
    first = replace(row, canonical_product_key="test-alias", product_name="test product",
                    retailer_id="test-store").with_id()
    second = replace(first, start_at=date(2026, 10, 8), case_id="existing-current-id")
    _remember_case(state, first)
    _remember_case(state, second)
    state.data["delivery_journal"][f"lottery:started:{second.case_id}"] = {
        "status": "complete", "updated_at": "2026-10-08T00:00:00+00:00",
    }
    prepared, count = _prepare_cases(state, [first, second])
    assert count == 0
    assert len(prepared) == 1
    assert prepared[0].case_id == second.case_id
    assert state.delivered(f"lottery:started:{prepared[0].case_id}")


def test_saved_route_duplicates_are_repaired_once_without_any_new_notifications(tmp_path):
    state = saved_state(tmp_path)
    calendar = Mock()
    calendar.reconcile.side_effect = lambda *args, **kwargs: {
        "status": "unchanged", "event_id": kwargs["known_event_id"],
    }
    calendar.delete_owned_event.return_value = {"status": "deleted"}
    config = load_config("sites.yaml")
    assert repair_social_route_duplicates(state, calendar, config) == 2
    assert calendar.reconcile.call_count == 2
    for retailer in ("seagull_common", "batoloco_morioka"):
        rows = [row for row in state.data["seen_cases"].values()
                if row["retailer_id"] == retailer
                and row["extraction_method"] == "yahoo_realtime_detected_open"]
        assert len(rows) == 1
        assert state.delivered(f"lottery:started:{rows[0]['case_id']}")
    state = MonitorState.load(state.path)
    calendar.reset_mock()
    assert repair_social_route_duplicates(state, calendar, config) == 0
    calendar.reconcile.assert_not_called()
