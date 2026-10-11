"""架空の案件だけで、初回取得・情報源交代・途中失敗を再現する。"""
from dataclasses import replace
from datetime import date
from unittest.mock import Mock

import httpx
import pytest

from tcg_monitor.cli import _cleanup_duplicate_lottery_events, _prepare_cases, _remember_case
from tcg_monitor.config import load_config
from tcg_monitor.discord import DiscordAdapter
from tcg_monitor.lottery_state_repair import repair_result_histories
from tcg_monitor.models import LotteryCase, SourceTier, stable_url_identity
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState


def campaign(**changes):
    row = LotteryCase(
        game_id="pokemon_card", retailer_id="test_store", retailer_name="試験店舗",
        product_name="30th CELEBRATION カードセット", product_category="カードセット",
        canonical_product_key="pokemon_30th_cardset", start_at=date(2026, 10, 11),
        official_url="https://forms.example/draw/one",
        source_url="https://x.com/synthetic_store/status/1234567890123456789",
        source_tier=SourceTier.OFFICIAL_INDIRECT,
        extraction_method="yahoo_realtime_detected_open", confidence="low",
    )
    return replace(row, **changes).with_id()


@pytest.mark.parametrize("reverse", [False, True])
def test_first_discovery_merges_same_post_with_confirmed_start(tmp_path, reverse):
    observed = campaign()
    confirmed = campaign(start_at=date(2026, 10, 10),
                         extraction_method="yahoo_realtime_body_application_period")
    rows = [observed, confirmed]
    if reverse:
        rows.reverse()
    state = MonitorState(tmp_path / "state.json")
    prepared, count = _prepare_cases(state, rows)
    assert len(prepared) == count == 1
    assert prepared[0].start_at == confirmed.start_at
    _remember_case(state, prepared[0])
    state.mark_delivered(f"lottery:started:{prepared[0].case_id}")
    restarted = MonitorState.load(state.path)
    prepared, count = _prepare_cases(restarted, rows)
    assert len(prepared) == 1 and count == 0
    assert restarted.delivered(f"lottery:started:{prepared[0].case_id}")


def test_result_history_and_calendar_identity_follow_campaign_migration(tmp_path):
    old = campaign(canonical_product_key="test-box", product_name="試験BOX",
                   case_id="unused")
    current = replace(old, source_url="https://news.example/draw/one").with_id()
    state = MonitorState(tmp_path / "state.json")
    _remember_case(state, old)
    for kind in ("started", "result"):
        state.data["delivery_journal"][f"lottery:{kind}:{old.case_id}"] = {
            "status": "complete", "updated_at": "2026-10-11T00:00:00+00:00",
        }
    state.data["calendar_sync"][f"lottery_result:{old.case_id}"] = {
        "event_id": "synthetic-result-event", "payload_hash": "synthetic",
    }
    state.migrate_case_identity(current)
    state.save()
    restarted = MonitorState.load(state.path)
    assert restarted.delivered(f"lottery:result:{current.case_id}")
    assert not restarted.delivered(f"lottery:result:{old.case_id}")
    assert restarted.data["calendar_sync"][f"lottery_result:{current.case_id}"][
        "event_id"
    ] == "synthetic-result-event"
    assert f"lottery_result:{old.case_id}" not in restarted.data["calendar_sync"]


def test_explicit_application_rounds_stay_separate_even_on_same_day(tmp_path):
    rows = [campaign(extraction_method="confirmed", application_round=round_name)
            for round_name in ("1次", "2次")]
    prepared, _ = _prepare_cases(MonitorState(tmp_path / "state.json"), rows)
    assert len(prepared) == 2
    assert len({row.case_id for row in prepared}) == 2


def test_same_social_post_aliases_have_one_identity():
    canonical = "https://x.com/synthetic_store/status/1234567890123456789"
    variant = "https://twitter.com/synthetic_store/status/1234567890123456789?s=20&t=tracking"
    assert stable_url_identity(variant) == stable_url_identity(canonical)
    rows = [campaign(source_url=url, official_url=url) for url in (canonical, variant)]
    assert len(merge_lotteries(rows)[0]) == 1


def test_missing_webhook_cannot_silently_consume_notifications(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    with pytest.raises(RuntimeError, match="DISCORD_WEBHOOK_URL"):
        DiscordAdapter().send("試験", "送信しない")
    assert DiscordAdapter(dry_run=True).send("試験", "送信しない")["status"] == "dry_run"


def test_round_migration_never_consumes_other_rounds_delivery(tmp_path):
    first = campaign(extraction_method="confirmed", application_round="1次")
    first = merge_lotteries([first])[0][0]
    state = MonitorState(tmp_path / "state.json")
    _remember_case(state, first)
    state.mark_delivered(f"lottery:started:{first.case_id}")
    second = campaign(extraction_method="confirmed", application_round="2次")
    prepared, count = _prepare_cases(state, [first, second])
    assert len(prepared) == 2 and count == 1
    assert sum(state.delivered(f"lottery:started:{row.case_id}") for row in prepared) == 1


def test_missing_round_is_enriched_only_when_unique(tmp_path):
    missing = campaign(extraction_method="confirmed", product_name="試験BOX",
                       canonical_product_key="test-box")
    first = replace(missing, application_round="1次",
                    source_url="https://news.example/first").with_id()
    assert len(merge_lotteries([missing, first])[0]) == 1
    second = replace(first, application_round="2次").with_id()
    assert len(merge_lotteries([missing, first, second])[0]) == 3
    state = MonitorState(tmp_path / "state.json")
    _remember_case(state, missing)
    state.mark_delivered(f"lottery:started:{missing.case_id}")
    prepared, count = _prepare_cases(state, [first])
    assert len(prepared) == 1 and count == 0
    assert state.delivered(f"lottery:started:{prepared[0].case_id}")


def test_observed_start_cannot_borrow_a_different_application_round(tmp_path):
    initial = merge_lotteries([campaign()])[0][0]
    next_round = campaign(application_round="2次")
    state = MonitorState(tmp_path / "state.json")
    _remember_case(state, initial)
    state.mark_delivered(f"lottery:started:{initial.case_id}")
    prepared, count = _prepare_cases(state, [initial, next_round])
    assert len(prepared) == 2 and count == 1
    assert sum(state.delivered(f"lottery:started:{row.case_id}") for row in prepared) == 1


def test_reference_aliasing_keeps_conflicting_deadlines_and_forms_separate():
    observed = campaign(end_at=date(2026, 10, 12))
    later = campaign(extraction_method="confirmed", end_at=date(2026, 11, 12))
    assert len(merge_lotteries([observed, later])[0]) == 2
    unrelated = campaign(extraction_method="confirmed",
                         official_url="https://forms.example/draw/two",
                         source_url="https://x.com/synthetic_store/status/2234567890123456789")
    assert len(merge_lotteries([campaign(), unrelated])[0]) == 2
    # 共有クエリだけを削り、フォームの応募先識別子は残す。
    assert stable_url_identity("https://forms.example/draw?s=one") != stable_url_identity(
        "https://forms.example/draw?s=two",
    )


def test_result_history_keeps_its_own_calendar_owner_and_retry_progress(tmp_path):
    state = MonitorState(tmp_path / "state.json")
    row = campaign(result_at=date(2026, 10, 12))
    _remember_case(state, row)
    state.data["case_id_migrations"][row.case_id] = {
        "calendar_identity": "start-owner", "legacy_ids": ["old-result"],
    }
    state.data["case_id_migrations"]["old-result"] = {"calendar_identity": "result-owner"}
    state.data["delivery_journal"]["lottery:result:old-result"] = {
        "status": "complete", "updated_at": "2026-10-11T00:00:00+00:00",
    }
    state.data["calendar_sync"]["lottery_result:old-result"] = {
        "event_id": "synthetic-result-event", "payload_hash": "synthetic",
    }
    calendar = Mock()
    calendar.reconcile.side_effect = RuntimeError("synthetic temporary failure")
    config = load_config("sites.yaml")
    with pytest.raises(RuntimeError, match="synthetic temporary failure"):
        repair_result_histories(state, calendar, config)
    restarted = MonitorState.load(state.path)
    assert restarted.delivered(f"lottery:result:{row.case_id}")
    assert restarted.calendar_case_identity(row.case_id) == "start-owner"
    assert restarted.calendar_case_identity(row.case_id, kind="lottery_result") == "result-owner"
    calendar.reconcile.side_effect = None
    calendar.reconcile.return_value = {"status": "unchanged", "event_id": "synthetic-result-event"}
    assert repair_result_histories(restarted, calendar, config) == 1
    assert calendar.reconcile.call_args.args[:2] == ("lottery_result", "result-owner")
    calendar.reset_mock()
    assert repair_result_histories(MonitorState.load(state.path), calendar, config) == 0
    calendar.reconcile.assert_not_called()


def test_result_duplicate_cleanup_retries_without_touching_start_events(tmp_path):
    state = MonitorState(tmp_path / "state.json")
    row = campaign(result_at=date(2026, 10, 12))
    _remember_case(state, row)
    for old_id in (row.case_id, "old-result"):
        state.data["calendar_sync"][f"lottery_result:{old_id}"] = {
            "event_id": f"synthetic-{old_id}",
        }
    state.migrate_result_history(row.case_id, ["old-result"])
    calendar = Mock()
    calendar.reconcile.return_value = {
        "status": "unchanged", "event_id": f"synthetic-{row.case_id}",
    }
    calendar.delete_owned_event.side_effect = [
        RuntimeError("temporary failure"), {"status": "deleted"},
    ]
    _cleanup_duplicate_lottery_events(state, calendar, row, "応募", "応募説明")
    calendar.reconcile.assert_not_called()
    with pytest.raises(RuntimeError, match="temporary failure"):
        _cleanup_duplicate_lottery_events(
            state, calendar, row, "結果", "結果説明", kind="lottery_result",
        )
    restarted = MonitorState.load(state.path)
    _cleanup_duplicate_lottery_events(
        restarted, calendar, row, "結果", "結果説明", kind="lottery_result",
    )
    calendar.delete_owned_event.assert_called_with(
        "synthetic-old-result", kind="lottery_result", internal_id="old-result",
    )
    calendar.reset_mock()
    _cleanup_duplicate_lottery_events(
        restarted, calendar, row, "結果", "結果説明", kind="lottery_result",
    )
    calendar.reconcile.assert_not_called()


def test_discord_preserves_webhook_query_and_requires_acknowledgment(monkeypatch):
    urls = []

    def post(url, **kwargs):
        urls.append(httpx.URL(url))
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    assert DiscordAdapter(webhook_url="https://example.com/mock?thread_id=synthetic").send(
        "試験", "合成データ",
    )["status"] == "sent"
    assert urls[0].params["wait"] == "true"
    assert urls[0].params["thread_id"] == "synthetic"


def test_provisional_title_cleanup_also_preserves_result_delivery(tmp_path):
    state = MonitorState(tmp_path / "state.json")
    row = campaign(product_name="試験BOX", canonical_product_key="test-box")
    _remember_case(state, row)
    old = replace(row, product_name="対象商品", case_id="provisional-title")
    _remember_case(state, old)
    state.data["delivery_journal"]["lottery:result:provisional-title"] = {
        "status": "complete", "updated_at": "2026-10-11T00:00:00+00:00",
    }
    state.migrate_case_identity(row)
    assert state.delivered(f"lottery:result:{row.case_id}")
    assert "provisional-title" not in state.data["seen_cases"]
    assert not state.delivered("lottery:result:provisional-title")
