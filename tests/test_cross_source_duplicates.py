"""実配信で二重通知された応募を、両方の到着順と再起動を含めて再現する。"""
import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest

from tcg_monitor.cli import _prepare_cases, _remember_case
from tcg_monitor.config import load_config
from tcg_monitor.identity import same_lottery_campaign
from tcg_monitor.lottery_state_repair import _case, repair_cross_source_duplicates
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState


def pairs():
    rows = json.loads((Path(__file__).parent / 'fixtures'
                       / 'cross_source_duplicates_20261031.json').read_text())
    for retailer in (
        'aeon_style_online', 'geo', 'kids_republic', 'premium_bandai', 'fullcomp', 'furuichi',
    ):
        yield [_case(row) for row in rows if row['retailer_id'] == retailer]


@pytest.mark.parametrize(
    'rows', list(pairs()), ids=['aeon', 'geo', 'kids', 'pbandai', 'fullcomp', 'furuichi'],
)
@pytest.mark.parametrize('reverse', [False, True])
def test_real_duplicates_notify_once_in_both_orders_and_after_restart(tmp_path, rows, reverse):
    if reverse:
        rows = rows[::-1]
    assert len(merge_lotteries(rows)[0]) == 1
    state = MonitorState(tmp_path / 'state.json')
    for index, row in enumerate(rows):
        prepared, _ = _prepare_cases(state, [row])
        assert len(prepared) == 1
        case = prepared[0]
        assert state.delivered(f'lottery:started:{case.case_id}') is (index != 0)
        _remember_case(state, case)
        state.mark_delivered(f'lottery:started:{case.case_id}')
        state.save()
        state = MonitorState.load(state.path)
    prepared, _ = _prepare_cases(state, rows)
    assert len(prepared) == 1
    assert state.delivered(f'lottery:started:{prepared[0].case_id}')


def test_separate_store_round_product_and_next_window_are_not_suppressed():
    explicit = next(row for rows in pairs() for row in rows
                    if row.retailer_id == 'premium_bandai' and row.end_at is not None)
    for change in (
        {'retailer_id': 'other_store'},
        {'application_round': 'second'},
        {'product_name': '世界最強の戦士【OP-17】', 'canonical_product_key': 'OP-17'},
        {'start_at': date(2026, 11, 30), 'end_at': date(2026, 12, 5)},
    ):
        first = replace(explicit, application_round='first') if 'application_round' in change else (
            explicit
        )
        assert not same_lottery_campaign(first, replace(explicit, **change))
        assert len(merge_lotteries([first, replace(explicit, **change)])[0]) == 2
    observed = next(row for rows in pairs() for row in rows
                    if row.retailer_id == 'premium_bandai' and row.end_at is None)
    assert not same_lottery_campaign(explicit, replace(observed, end_at=date(2026, 12, 5)))
    # 10月の投稿を11月の巡回で再取得しても、新しい募集の履歴を借りない。
    assert not same_lottery_campaign(
        replace(explicit, start_at=date(2026, 11, 1), end_at=date(2026, 11, 5)), observed,
    )


def test_existing_duplicate_deliveries_and_calendar_ids_are_preserved(tmp_path):
    state = MonitorState(tmp_path / 'state.json')
    rows = next(rows for rows in pairs() if rows[0].retailer_id == 'geo')
    for index, row in enumerate(rows):
        _remember_case(state, row)
        state.data['delivery_journal'][f'lottery:started:{row.case_id}'] = {
            'status': 'complete', 'updated_at': f'2026-10-30T0{index}:00:00+00:00',
        }
        state.data['calendar_sync'][f'lottery:{row.case_id}'] = {
            'status': 'updated', 'event_id': f'synthetic-event-{index}',
        }
    prepared, _ = _prepare_cases(state, rows)
    assert len(prepared) == 1
    case = prepared[0]
    assert len(state.data['seen_cases']) == 1
    assert state.data['delivery_journal'][f'lottery:started:{case.case_id}']['updated_at'] == (
        '2026-10-30T00:00:00+00:00'
    )
    migration = state.data['case_id_migrations'][case.case_id]
    assert len(migration['duplicate_calendar_events']) == 1
    assert state.data['calendar_sync'][f'lottery:{case.case_id}']['event_id'] == 'synthetic-event-0'


@pytest.mark.parametrize("interrupt", [False, True])
def test_saved_recent_duplicates_are_repaired_without_discord_and_are_restart_safe(
    tmp_path, interrupt,
):
    state = MonitorState(tmp_path / 'state.json')
    for rows in pairs():
        for index, row in enumerate(rows):
            _remember_case(state, row)
            state.data['delivery_journal'][f'lottery:started:{row.case_id}'] = {
                'status': 'complete', 'updated_at': f'2026-10-30T0{index}:00:00+00:00',
            }
            state.data['calendar_sync'][f'lottery:{row.case_id}'] = {
                'status': 'updated', 'event_id': f'synthetic-{row.retailer_id}-{index}',
            }
    calendar = Mock()
    calendar.reconcile.side_effect = lambda *args, **kwargs: {
        'status': 'unchanged', 'event_id': kwargs['known_event_id'],
    }
    calendar.delete_owned_event.return_value = {'status': 'deleted'}
    config = load_config('sites.yaml')
    if interrupt:
        calendar.delete_owned_event.side_effect = RuntimeError("temporary calendar failure")
        with pytest.raises(RuntimeError, match="temporary calendar failure"):
            repair_cross_source_duplicates(state, calendar, config)
        state = MonitorState.load(state.path)
        calendar.reset_mock()
        calendar.delete_owned_event.side_effect = None
    assert repair_cross_source_duplicates(state, calendar, config) == 6
    assert len(state.data['seen_cases']) == 6
    assert calendar.delete_owned_event.call_count == 6
    for row in state.data['seen_cases'].values():
        assert state.delivered(f"lottery:started:{row['case_id']}")
    calendar.reset_mock()
    restored = MonitorState.load(state.path)
    assert repair_cross_source_duplicates(restored, calendar, config) == 0
    calendar.reconcile.assert_not_called()
    calendar.delete_owned_event.assert_not_called()
