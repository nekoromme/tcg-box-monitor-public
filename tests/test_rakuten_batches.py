"""実運用の6記録・5商品と、境界・再実行・部分失敗で集約を確認する。"""

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import httpx
import pytest
from freezegun import freeze_time

from tcg_monitor import cli
from tcg_monitor.config import load_config
from tcg_monitor.discord import (
    DISCORD_SAFE_DESCRIPTION_LIMIT,
    DiscordAdapter,
    discord_text_length,
    split_discord_description,
)
from tcg_monitor.google_calendar import CalendarAdapter
from tcg_monitor.models import LotteryCase, OpportunityKind, SourceTier
from tcg_monitor.rakuten_batches import (
    RakutenBatch,
    _saved_case,
    already_grouped,
    build_rakuten_batches,
    sync_rakuten_batch,
)
from tcg_monitor.state import MonitorState

CONFIG = load_config("sites.yaml")
TODAY = date(2026, 10, 9)
JST = ZoneInfo("Asia/Tokyo")


def products(count=4):
    return [LotteryCase(
        game_id="pokemon_card" if i % 2 else "one_piece_card", retailer_id="rakuten_books",
        retailer_name="楽天ブックス", product_name=f"試験商品{i}", product_category="BOX",
        canonical_product_key=f"test-{i}", start_at=datetime(2026, 10, 14, 10, tzinfo=JST),
        official_url=f"https://books.rakuten.co.jp/rb/{10000000 + i}/?slide=modal",
        source_url="https://books.rakuten.co.jp/event/toy/lottery/",
        source_tier=SourceTier.OFFICIAL, extraction_method="rakuten_detail_application_period",
        confidence="high", end_at=datetime(2026, 10, 18, 23, 59, tzinfo=JST),
    ).with_id() for i in range(count)]


def adapters():
    calendar = MagicMock(spec=CalendarAdapter)
    calendar.reconcile.return_value = {"status": "inserted", "event_id": "batch-event"}
    calendar.delete_owned_event.return_value = {"status": "deleted"}
    discord = MagicMock(spec=DiscordAdapter)
    discord.send.return_value = {"status": "sent"}
    return calendar, discord


def test_threshold_counts_distinct_urls_not_games_aliases_or_tracking(tmp_path):
    state = MonitorState(tmp_path / "state.json")
    items = products(3)
    alias = replace(items[0], product_name="別表記", canonical_product_key="別表記",
                    official_url=items[0].official_url.split("?")[0] + "?bkts=1").with_id()
    assert build_rakuten_batches(state, [*items, alias], CONFIG, TODAY) == []
    batches = build_rakuten_batches(state, [*products(), alias], CONFIG, TODAY)
    assert len(batches) == 1 and len(batches[0].urls) == 4 and len(batches[0].cases) == 5
    assert all("?" not in url for url in batches[0].urls)


def test_same_japan_day_groups_different_times_but_not_unknown_dates_sales_or_other_stores(
    tmp_path,
):
    state = MonitorState(tmp_path / "state.json")
    items = products()
    items[0] = replace(items[0], start_at=datetime(2026, 10, 13, 17, tzinfo=UTC))
    batch = build_rakuten_batches(state, items, CONFIG, TODAY)[0]
    assert batch.day == date(2026, 10, 14)
    assert batch.when == datetime(2026, 10, 14, 2, tzinfo=JST)
    assert "2026/10/14 02:00" in batch.description
    assert "2026/10/13" not in batch.description
    for fields in (
        {"start_at": date(2026, 10, 15)}, {"retailer_id": "other"},
        {"opportunity_kind": OpportunityKind.DIRECT_SALE},
        {"extraction_method": "yahoo_realtime_detected_next_day"},
        {"official_url": "https://books.rakuten.co.jp/event/toy/lottery/"},
    ):
        assert build_rakuten_batches(state, [*items[1:], replace(items[0], **fields)],
                                    CONFIG, TODAY) == []
    assert build_rakuten_batches(state, items, CONFIG, date(2026, 10, 20)) == []
    batch = build_rakuten_batches(state, [replace(case, start_at=batch.day) for case in items],
                                 CONFIG, TODAY)[0]
    assert batch.when == batch.day


def test_actual_saved_six_records_become_five_urls_without_renotification(tmp_path):
    state = MonitorState(tmp_path / "state.json")
    state.data.update(json.loads(Path(
        "tests/fixtures/rakuten_same_day_state_20261009.json",
    ).read_text()))
    # 本番と同じ旧IDを新しい日付別IDへ移し、配信・予定の履歴を引き継ぐ。
    current = [_saved_case(case_id, record).with_id()
               for case_id, record in state.data["seen_cases"].items()
               if record["start_at"].startswith("2026-10-14")]
    current, _ = cli._prepare_cases(state, current)
    batches = build_rakuten_batches(state, current, CONFIG, TODAY)
    assert len(batches) == 1
    batch = batches[0]
    assert len(batch.cases) == 6 and len(batch.urls) == 5
    calendar, discord = adapters()
    sync_rakuten_batch(state, calendar, discord, batch)
    discord.send.assert_not_called()
    assert calendar.delete_owned_event.call_count == 6
    assert all(call.kwargs["expected_day"] == date(2026, 10, 14)
               for call in calendar.delete_owned_event.call_args_list)
    assert calendar.reconcile.call_args.args[2] == "【抽選】楽天ブックス／全5種"
    assert calendar.reconcile.call_args.args[3] == datetime(2026, 10, 14, 10, tzinfo=JST)
    assert batch.description.count("https://books.rakuten.co.jp/rb/") == 5
    assert "抽出方法" not in batch.description and "商品:" not in batch.description
    # 古い別表記が同じ予定IDを参照していても、商品別予定を復活させない。
    for case_id, record in state.data["seen_cases"].items():
        assert already_grouped(state, _saved_case(case_id, record))
    state = MonitorState.load(state.path)
    partial = [batch.cases[0]]
    assert len(build_rakuten_batches(state, partial, CONFIG, TODAY)[0].urls) == 5
    sync_rakuten_batch(state, calendar, discord,
                       build_rakuten_batches(state, partial, CONFIG, TODAY)[0])
    assert calendar.delete_owned_event.call_count == 6
    discord.send.assert_not_called()


def test_new_batch_once_then_addition_updates_same_event_and_notifies_once(tmp_path):
    state = MonitorState(tmp_path / "state.json")
    calendar, discord = adapters()
    batch = build_rakuten_batches(state, products(), CONFIG, TODAY)[0]
    sync_rakuten_batch(state, calendar, discord, batch)
    assert discord.send.call_count == 1
    assert discord.send.call_args.args[0] == "【抽選】楽天ブックス／全4種"
    assert all(state.delivered(f"lottery:started:{case.case_id}") for case in batch.cases)
    state = MonitorState.load(state.path)
    next_batch = build_rakuten_batches(state, [products(5)[-1]], CONFIG, TODAY)[0]
    sync_rakuten_batch(state, calendar, discord, next_batch)
    assert discord.send.call_count == 2
    assert discord.send.call_args.args[0] == "【抽選】楽天ブックス／全5種（追加1種）"
    assert discord.send.call_args.args[1].count("https://books.rakuten.co.jp/rb/") == 1
    assert calendar.reconcile.call_args.kwargs["known_event_id"] == "batch-event"
    sync_rakuten_batch(MonitorState.load(state.path), calendar, discord, next_batch)
    assert discord.send.call_count == 2
    # 翌日の別抽選は通知済みとして抑制しない。
    future = [replace(case, start_at=date(2026, 10, 15),
                      application_round="next").with_id() for case in products()]
    next_day = build_rakuten_batches(state, future, CONFIG, TODAY)[-1]
    sync_rakuten_batch(state, calendar, discord, next_day)
    assert discord.send.call_count == 3 and next_day.internal_id != batch.internal_id


def test_calendar_failure_does_not_delete_or_mark_notified(tmp_path):
    state = MonitorState(tmp_path / "state.json")
    batch = build_rakuten_batches(state, products(), CONFIG, TODAY)[0]
    calendar, discord = adapters()
    calendar.reconcile.return_value = {"status": "dry_run"}
    with pytest.raises(RuntimeError, match="集約予定"):
        sync_rakuten_batch(state, calendar, discord, batch)
    calendar.delete_owned_event.assert_not_called()
    discord.send.assert_not_called()
    assert state.data["delivery_journal"] == {}


def test_send_failure_retries_full_batch_after_partial_fetch(tmp_path):
    state = MonitorState(tmp_path / "state.json")
    batch = build_rakuten_batches(state, products(), CONFIG, TODAY)[0]
    calendar, discord = adapters()
    discord.send.side_effect = RuntimeError("試験送信失敗")
    with pytest.raises(RuntimeError, match="試験送信失敗"):
        sync_rakuten_batch(state, calendar, discord, batch)
    progress = state.data["delivery_journal"][f"{batch.sync_key}:notification"]
    assert progress["status"] == "in_progress"
    assert all(part["status"] == "pending" for part in progress["parts"])
    assert all(not state.delivered(f"lottery:started:{case.case_id}") for case in batch.cases)
    calendar.delete_owned_event.assert_not_called()
    state = MonitorState.load(state.path)
    retry = build_rakuten_batches(state, [batch.cases[0]], CONFIG, TODAY)[0]
    assert len(retry.urls) == 4
    discord.send.side_effect = None
    sync_rakuten_batch(state, calendar, discord, retry)
    assert all(state.delivered(f"lottery:started:{case.case_id}") for case in batch.cases)


def test_delete_failure_retries_without_resending_and_cleans_legacy_duplicates(tmp_path):
    state = MonitorState(tmp_path / "state.json")
    batch = build_rakuten_batches(state, products(), CONFIG, TODAY)[0]
    case = batch.cases[0]
    state.data["calendar_sync"][f"lottery:{case.case_id}"] = {"event_id": "old-event"}
    duplicate = {"event_id": "legacy-event", "internal_id": "legacy-id"}
    state.data["case_id_migrations"][case.case_id] = {
        "duplicate_calendar_events": {"legacy": duplicate},
    }
    calendar, discord = adapters()
    calendar.delete_owned_event.side_effect = RuntimeError("試験削除失敗")
    with pytest.raises(RuntimeError, match="試験削除失敗"):
        sync_rakuten_batch(state, calendar, discord, batch)
    assert discord.send.call_count == 1
    calendar.delete_owned_event.side_effect = None
    state = MonitorState.load(state.path)
    sync_rakuten_batch(state, calendar, discord, batch)
    assert discord.send.call_count == 1
    assert state.data["case_id_migrations"][case.case_id][
        "duplicate_calendar_events"]["legacy"]["status"] == "deleted"


@freeze_time("2026-10-09T03:00:00Z")
def test_live_cli_uses_one_batch_then_keeps_three_product_delivery(tmp_path, monkeypatch):
    cases = products()
    calendar, discord = adapters()
    calendar.upsert.return_value = {"status": "inserted", "event_id": "individual-event"}
    monkeypatch.setattr(cli, "run_pipeline", lambda *a, **kw: (cases, [], []))
    monkeypatch.setattr(cli, "CalendarAdapter", lambda: calendar)
    monkeypatch.setattr(cli, "DiscordAdapter", lambda: discord)
    monkeypatch.setattr(cli, "run_purchase_reviews", lambda *a: [])
    state = MonitorState(tmp_path / "state.json")
    state.mark_baseline()
    state.arm()
    assert cli.main(["--state", str(state.path), "run"]) == 0
    assert discord.send.call_count == 1
    calendar.upsert.assert_not_called()
    assert cli.main(["--state", str(state.path), "run"]) == 0
    assert discord.send.call_count == 1
    # 日付が異なる3種類は、従来の個別通知と個別予定を保つ。
    cases[:] = [replace(case, start_at=date(2026, 10, 16),
                        application_round="separate").with_id() for case in products(3)]
    assert cli.main(["--state", str(state.path), "run"]) == 0
    assert discord.send.call_count == 4 and calendar.upsert.call_count == 3


def test_reused_product_url_has_a_new_identity_on_the_next_start_day(tmp_path):
    state = MonitorState(tmp_path / "state.json")
    first = products()[0]
    state.data["seen_cases"][first.case_id] = first.__dict__
    state.mark_delivered(f"lottery:started:{first.case_id}")
    next_draw = replace(first, start_at=date(2026, 10, 16)).with_id()
    assert next_draw.case_id != first.case_id
    assert state.migrate_case_identity(next_draw) is None
    assert not state.delivered(f"lottery:started:{next_draw.case_id}")
    assert first.case_id in state.data["seen_cases"]


def test_saved_products_respect_game_and_source_scope(tmp_path):
    state = MonitorState(tmp_path / "state.json")
    for case in products():
        state.data["seen_cases"][case.case_id] = case.__dict__
    assert build_rakuten_batches(state, [], CONFIG, TODAY, include_saved=False) == []
    config = replace(CONFIG, enabled_game_ids=frozenset({"pokemon_card"}))
    assert build_rakuten_batches(state, [], config, TODAY) == []


def test_batch_description_keeps_all_deadlines_explicitly_unconfirmed_when_different():
    items = products()
    items[0] = replace(items[0], end_at=date(2026, 10, 17))
    batch = RakutenBatch(date(2026, 10, 14), tuple(items))
    assert "締切は各リンク先で確認" in batch.description
    assert "応募締切:" not in batch.description


@pytest.mark.parametrize(("count", "message_count"), [(20, 1), (100, 2), (200, 3)])
def test_large_batch_splits_without_missing_urls_and_keeps_one_calendar(
    tmp_path, count, message_count,
):
    state = MonitorState(tmp_path / "state.json")
    batch = build_rakuten_batches(state, products(count), CONFIG, TODAY)[0]
    calendar, discord = adapters()
    sync_rakuten_batch(state, calendar, discord, batch)
    calls = discord.send.call_args_list
    assert len(calls) == message_count
    assert "".join(call.args[1] for call in calls) == batch.description
    notified = [line for call in calls for line in call.args[1].splitlines()
                if line.startswith("https://books.rakuten.co.jp/rb/")]
    assert notified == list(batch.urls)
    assert all(discord_text_length(call.args[1]) <= DISCORD_SAFE_DESCRIPTION_LIMIT
               for call in calls)
    for index, call in enumerate(calls, start=1):
        assert f"全{count}種" in call.args[0]
        if message_count > 1:
            assert call.args[0].endswith(f"・{index}/{message_count}")
    assert calendar.reconcile.call_count == 1
    assert calendar.reconcile.call_args.args[4] == batch.description
    sync_rakuten_batch(MonitorState.load(state.path), calendar, discord, batch)
    assert discord.send.call_count == message_count


def test_split_batch_reaches_discord_payload_without_truncation(tmp_path, monkeypatch):
    payloads = []

    def capture_post(url, *, json, timeout):
        payloads.append(json)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", capture_post)
    state = MonitorState(tmp_path / "state.json")
    batch = build_rakuten_batches(state, products(200), CONFIG, TODAY)[0]
    calendar, _ = adapters()
    sync_rakuten_batch(state, calendar, DiscordAdapter(webhook_url="https://example.com/mock"),
                       batch)
    embeds = [payload["embeds"][0] for payload in payloads]
    assert len(embeds) == 3
    assert "".join(embed["description"] for embed in embeds) == batch.description
    assert all(discord_text_length(embed["description"]) <= DISCORD_SAFE_DESCRIPTION_LIMIT
               for embed in embeds)
    assert embeds[-1]["title"] == "【抽選】楽天ブックス／全200種・3/3"


def test_failed_second_part_resumes_unchanged_remaining_parts_after_reload(tmp_path):
    state = MonitorState(tmp_path / "state.json")
    batch = build_rakuten_batches(state, products(200), CONFIG, TODAY)[0]
    parts = split_discord_description(batch.description)
    calendar, discord = adapters()
    discord.send.side_effect = [{"status": "sent"}, RuntimeError("分割2件目の送信失敗")]
    with pytest.raises(RuntimeError, match="分割2件目"):
        sync_rakuten_batch(state, calendar, discord, batch)
    state = MonitorState.load(state.path)
    progress = state.data["delivery_journal"][f"{batch.sync_key}:notification"]
    assert [part["status"] for part in progress["parts"]] == ["complete", "pending", "pending"]
    assert not all(state.delivered(f"lottery:started:{case.case_id}") for case in batch.cases)
    retry = build_rakuten_batches(state, [batch.cases[0]], CONFIG, TODAY)[0]
    _, resumed_discord = adapters()
    sync_rakuten_batch(state, calendar, resumed_discord, retry)
    assert [call.args[1] for call in resumed_discord.send.call_args_list] == list(parts[1:])
    assert [call.args[0] for call in resumed_discord.send.call_args_list] == [
        "【抽選】楽天ブックス／全200種・2/3", "【抽選】楽天ブックス／全200種・3/3",
    ]
    assert state.data["delivery_journal"][f"{batch.sync_key}:notification"]["status"] == "complete"
    sync_rakuten_batch(MonitorState.load(state.path), calendar, resumed_discord, retry)
    assert resumed_discord.send.call_count == 2


def test_new_items_during_partial_delivery_finish_old_parts_then_notify_only_additions(tmp_path):
    state = MonitorState(tmp_path / "state.json")
    batch = build_rakuten_batches(state, products(100), CONFIG, TODAY)[0]
    calendar, discord = adapters()
    discord.send.side_effect = [{"status": "sent"}, RuntimeError("送信失敗")]
    with pytest.raises(RuntimeError, match="送信失敗"):
        sync_rakuten_batch(state, calendar, discord, batch)
    state = MonitorState.load(state.path)
    updated = build_rakuten_batches(state, products(105)[100:], CONFIG, TODAY)[0]
    _, retry_discord = adapters()
    sync_rakuten_batch(state, calendar, retry_discord, updated)
    assert [call.args[0] for call in retry_discord.send.call_args_list] == [
        "【抽選】楽天ブックス／全100種・2/2", "【抽選】楽天ブックス／全105種（追加5種）",
    ]
    assert retry_discord.send.call_args_list[-1].args[1].count(
        "https://books.rakuten.co.jp/rb/",
    ) == 5
    assert all(state.delivered(f"lottery:started:{case.case_id}") for case in updated.cases)


def test_split_counts_emoji_conservatively_and_never_breaks_a_url():
    url = "https://books.rakuten.co.jp/rb/10000000/"
    text = "😀" * 1900 + "\n" + url
    parts = split_discord_description(text)
    assert len(parts) == 2 and "".join(parts) == text
    assert all(discord_text_length(part) <= DISCORD_SAFE_DESCRIPTION_LIMIT for part in parts)
    assert any(url in part.splitlines() for part in parts)
    # URLの文字数ちょうどで分割してもURL自体は割らない。
    parts = split_discord_description(url + "\n次の行", limit=len(url))
    assert parts[0] == url and "".join(parts) == url + "\n次の行"
    with pytest.raises(ValueError, match="URL"):
        split_discord_description(url, limit=10)
