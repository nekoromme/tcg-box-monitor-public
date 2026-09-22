"""9種類の通知集約と、旧版の配信履歴からの移行を検証する。"""
from dataclasses import replace
from datetime import date
from pathlib import Path

from tcg_monitor.models import LotteryCase, SourceTier
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState


def variants() -> list[LotteryCase]:
    return [
        LotteryCase(
            "pokemon_card", "shop", "店舗", f"30th CELEBRATION カードセット 種類{i}",
            "カードセット", f"pokemon_30th_cardset:{i}", date(2026, 9, 21),
            f"https://example.com/item/{i}", f"https://example.com/item/{i}",
            SourceTier.OFFICIAL, "test", "high",
        ).with_id()
        for i in range(1, 10)
    ]


def test_nine_variants_and_generic_notice_become_one() -> None:
    items = variants()
    generic = replace(items[0], canonical_product_key="pokemon_30th_cardset")
    cases, alerts = merge_lotteries([*items, generic])
    assert not alerts and len(cases) == 1
    assert cases[0].product_name == "30th CELEBRATION カードセット"
    # 翌巡回で別の種類しか見つからなくても同じ通知IDになる。
    assert merge_lotteries([items[-1]])[0][0].case_id == cases[0].case_id


def test_other_store_round_and_box_stay_separate() -> None:
    first = variants()[0]
    other_store = replace(first, retailer_id="other")
    next_round = replace(first, start_at=date(2026, 10, 1))
    box = replace(first, canonical_product_key="30th", product_name="30th CELEBRATION")
    cases, _ = merge_lotteries([first, other_store, next_round, box])
    assert len(cases) == 4
    assert len({case.case_id for case in cases[:3]}) == 3


def test_legacy_delivery_is_reused_without_renotification(tmp_path: Path) -> None:
    items = variants()
    state = MonitorState(tmp_path / "state.json")
    for item in items:
        state.data["seen_cases"][item.case_id] = {
            **item.__dict__, "start_at": item.start_at.isoformat(),
        }
    delivered = items[-1]
    state.data["delivery_journal"][f"lottery:started:{delivered.case_id}"] = {
        "status": "complete", "updated_at": "2026-09-21T10:00:00+09:00",
    }
    grouped = merge_lotteries(items)[0][0]
    assert state.migrate_case_identity(grouped) == delivered.case_id
    assert state.delivered(f"lottery:started:{grouped.case_id}")
    assert state.calendar_case_identity(grouped.case_id) == delivered.case_id
    assert state.migrate_case_identity(grouped) is None
    next_round = merge_lotteries([replace(items[0], start_at=date(2026, 10, 1))])[0][0]
    assert state.migrate_case_identity(next_round) is None
    assert not state.delivered(f"lottery:started:{next_round.case_id}")
