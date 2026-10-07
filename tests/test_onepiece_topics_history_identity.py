"""実際の公式ニュース一覧が別商品の履歴を混線させる問題の回帰確認。"""
import json
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from tcg_monitor.cli import _prepare_cases, _remember_case
from tcg_monitor.models import LotteryCase, OpportunityKind, SourceTier
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState

FIXTURE = Path(__file__).parent / "fixtures/onepiece_topics_history_20261007.json"


def _cases(records: dict) -> list[LotteryCase]:
    cases = []
    for record in records.values():
        fields = dict(record)
        for key in ("start_at", "end_at", "result_at"):
            value = fields.get(key)
            if value:
                fields[key] = (datetime.fromisoformat(value) if len(value) > 10
                               else date.fromisoformat(value))
        fields["source_tier"] = SourceTier(fields["source_tier"])
        fields["opportunity_kind"] = OpportunityKind(fields["opportunity_kind"])
        cases.append(LotteryCase(**fields))
    return cases


@pytest.mark.parametrize("reverse", [False, True])
def test_real_topic_index_keeps_all_individual_product_histories(
    tmp_path: Path, reverse: bool,
) -> None:
    fixture = json.loads(FIXTURE.read_text())
    state = MonitorState(tmp_path / "state.json")
    state.data.update(fixture)
    cases = merge_lotteries(_cases(fixture["seen_cases"]))[0]
    if reverse:
        cases.reverse()
    prepared, count = _prepare_cases(state, cases)
    assert count == 0
    assert len(prepared) == len(fixture["seen_cases"])
    assert set(state.data["seen_cases"]) == set(fixture["seen_cases"])
    assert state.data["delivery_journal"] == fixture["delivery_journal"]
    for case in prepared:
        _remember_case(state, case)
    state.save()
    restored = MonitorState.load(state.path)
    assert _prepare_cases(restored, cases)[1] == 0
    assert set(restored.data["seen_cases"]) == set(fixture["seen_cases"])


def test_new_product_on_same_topic_index_is_not_marked_delivered(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE.read_text())
    state = MonitorState(tmp_path / "state.json")
    state.data.update(fixture)
    current = _cases(fixture["seen_cases"])[0]
    new = replace(current, product_name="新しいブースターパック OP-99 抽選販売",
                  canonical_product_key="OP-99", start_at=date(2026, 11, 1),
                  official_url="https://p-bandai.jp/item/item-1000999999/", case_id="").with_id()
    assert _prepare_cases(state, [new])[1] == 1
    assert not state.delivered(f"lottery:started:{new.case_id}")
    assert set(state.data["seen_cases"]) == set(fixture["seen_cases"])
