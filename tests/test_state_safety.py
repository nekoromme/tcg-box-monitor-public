from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

import tcg_monitor.cli as cli
import tcg_monitor.state as state_module
from tcg_monitor.google_calendar import CalendarAdapter
from tcg_monitor.models import LotteryCase, Release, SourceTier
from tcg_monitor.state import MonitorState


def _lottery(start_at: date) -> LotteryCase:
    return LotteryCase(
        "pokemon_card",
        "test_store",
        "テスト店舗",
        "拡張パック「テスト」",
        "拡張パック",
        "pokemon_card:test",
        start_at,
        "https://shop.example/lottery/42",
        "https://shop.example/news/42",
        SourceTier.OFFICIAL,
        "test",
        "high",
    ).with_id()


def _release(
    canonical_product_key: str,
    official_url: str,
) -> Release:
    return Release(
        "pokemon_card",
        "拡張パック「30th CELEBRATION」",
        "拡張パック",
        canonical_product_key,
        date(2026, 9, 16),
        None,
        official_url,
        official_url,
        SourceTier.OFFICIAL,
        "pokemon_official_product_card",
        "high",
    ).with_id()


def test_case_id_ignores_corrected_start_datetime() -> None:
    original = _lottery(date(2026, 7, 25))
    corrected = _lottery(date(2026, 7, 26))

    assert original.case_id == corrected.case_id


def test_case_migration_prefers_delivered_legacy_duplicate(tmp_path) -> None:
    case = _lottery(date(2026, 7, 26))
    state = MonitorState.load(tmp_path / "monitor_state.json")
    for legacy_id, start_at in (
        ("legacy-undelivered", "2026-07-25"),
        ("legacy-delivered", "2026-07-26"),
    ):
        state.data["seen_cases"][legacy_id] = {
            **case.__dict__,
            "case_id": legacy_id,
            "start_at": start_at,
        }
    state.data["delivery_journal"]["lottery:started:legacy-delivered"] = {
        "status": "complete",
        "updated_at": datetime.now(UTC).isoformat(),
    }

    migrated_from = state.migrate_case_identity(case)

    assert migrated_from == "legacy-delivered"
    assert set(state.data["seen_cases"]) == {case.case_id}
    assert state.calendar_case_identity(case.case_id) == "legacy-delivered"
    assert state.delivered(f"lottery:started:{case.case_id}")


def test_amazon_product_migration_collapses_multiple_social_posts(tmp_path) -> None:
    current = LotteryCase(
        "one_piece_card",
        "amazon_jp",
        "Amazon.co.jp",
        "エクストラブースター ONE PIECE Heroines Edition vol.2【EB-05】",
        "エクストラブースター",
        "EB-05",
        date(2026, 8, 11),
        "https://www.amazon.co.jp/dp/B0HB3JQ6P4",
        "https://snkrdunk.com/articles/32599/",
        SourceTier.SECONDARY,
        "snkrdunk_open_invitation_seen",
        "low",
    ).with_id()
    state = MonitorState.load(tmp_path / "monitor_state.json")
    old_ids = ("old-amazon-post-1", "old-amazon-post-2")
    for old_id, status_id, short_url in (
        (old_ids[0], "2087124342010491311", "https://t.co/tsRvSXw4cs"),
        (old_ids[1], "2087125238991696167", "https://t.co/mQkn1sqex5"),
    ):
        state.data["seen_cases"][old_id] = {
            **current.__dict__,
            "case_id": old_id,
            "official_url": short_url,
            "source_url": f"https://x.com/onepiecenyuka/status/{status_id}",
        }
    state.data["delivery_journal"][f"lottery:started:{old_ids[1]}"] = {
        "status": "complete",
        "updated_at": datetime.now(UTC).isoformat(),
    }

    migrated_from = state.migrate_case_identity(current)

    assert migrated_from == old_ids[1]
    assert set(state.data["seen_cases"]) == {current.case_id}
    assert state.delivered(f"lottery:started:{current.case_id}")
    assert not state.delivered(f"lottery:started:{old_ids[0]}")
    assert not state.delivered(f"lottery:started:{old_ids[1]}")
    assert state.calendar_case_identity(current.case_id) == old_ids[1]


def test_existing_correct_case_drops_provisional_duplicate_for_same_event(
    tmp_path,
) -> None:
    correct = _lottery(date(2026, 7, 26))
    provisional_id = "provisional-heading"
    state = MonitorState.load(tmp_path / "monitor_state.json")
    state.data["seen_cases"][correct.case_id] = correct.__dict__
    state.data["seen_cases"][provisional_id] = {
        **correct.__dict__,
        "case_id": provisional_id,
        "product_name": "拡張パック「当選者への連絡日」",
    }
    shared_event_id = "tcg-shared-event"
    for case_id in (correct.case_id, provisional_id):
        state.data["calendar_sync"][f"lottery:{case_id}"] = {
            "event_id": shared_event_id,
            "status": "updated",
        }
        state.data["delivery_journal"][f"lottery:started:{case_id}"] = {
            "status": "complete"
        }

    assert state.migrate_case_identity(correct) is None

    assert set(state.data["seen_cases"]) == {correct.case_id}
    assert f"lottery:{provisional_id}" not in state.data["calendar_sync"]
    assert (
        f"lottery:started:{provisional_id}"
        not in state.data["delivery_journal"]
    )
    assert state.delivered(f"lottery:started:{correct.case_id}")


def test_existing_correct_case_keeps_provisional_duplicate_with_other_event(
    tmp_path,
) -> None:
    correct = _lottery(date(2026, 7, 26))
    provisional_id = "provisional-other-event"
    state = MonitorState.load(tmp_path / "monitor_state.json")
    state.data["seen_cases"][correct.case_id] = correct.__dict__
    state.data["seen_cases"][provisional_id] = {
        **correct.__dict__,
        "case_id": provisional_id,
        "product_name": "拡張パック「対象商品」",
    }
    state.data["calendar_sync"][f"lottery:{correct.case_id}"] = {
        "event_id": "correct-event",
    }
    state.data["calendar_sync"][f"lottery:{provisional_id}"] = {
        "event_id": "other-event",
    }

    state.migrate_case_identity(correct)

    assert provisional_id in state.data["seen_cases"]


def test_legacy_case_id_updates_same_calendar_event(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path = tmp_path / "monitor_state.json"
    corrected = _lottery(date.today() + timedelta(days=1))
    legacy_id = "legacy-start-based-case-id"
    legacy_record = {
        **corrected.__dict__,
        "case_id": legacy_id,
        "start_at": str(date.today()),
    }
    state = MonitorState.load(state_path)
    state.data["seen_cases"][legacy_id] = legacy_record
    state.data["delivery_journal"][f"lottery:started:{legacy_id}"] = {
        "status": "complete",
        "updated_at": datetime.now(UTC).isoformat(),
    }
    state.data["baseline_complete"] = True
    state.data["armed"] = True
    state.save()

    calendar_calls: list[tuple[str, str]] = []
    discord_calls: list[str] = []

    class FakeCalendar:
        def upsert(
            self,
            kind: str,
            internal_id: str,
            _summary: str,
            _when: object,
            _description: str,
            dedupe_key: str | None = None,
        ) -> dict[str, str]:
            assert dedupe_key is None
            calendar_calls.append((kind, internal_id))
            return {
                "status": "updated",
                "event_id": CalendarAdapter(dry_run=True).event_id(kind, internal_id),
            }

    class FakeDiscord:
        def send(self, title: str, _description: str) -> dict[str, str]:
            discord_calls.append(title)
            return {"status": "sent"}

    monkeypatch.setattr(
        cli,
        "run_pipeline",
        lambda *_args, **_kwargs: ([corrected], [], []),
    )
    monkeypatch.setattr(cli, "CalendarAdapter", FakeCalendar)
    monkeypatch.setattr(cli, "DiscordAdapter", FakeDiscord)

    result = cli.main(
        [
            "--config",
            "sites.yaml",
            "--state",
            str(state_path),
            "run",
        ]
    )

    assert result == 0
    assert calendar_calls == [("lottery", legacy_id)]
    assert not discord_calls
    reloaded = MonitorState.load(state_path)
    assert corrected.case_id in reloaded.data["seen_cases"]
    assert legacy_id not in reloaded.data["seen_cases"]
    assert reloaded.calendar_case_identity(corrected.case_id) == legacy_id
    assert reloaded.delivered(f"lottery:started:{corrected.case_id}")


def test_release_identity_is_reused_across_different_catalog_urls(
    tmp_path,
) -> None:
    first = _release(
        "拡張パック「30thCELEBRATION」",
        "https://www.pokemon-card.com/products/index.html?productType=expansion",
    )
    duplicate = _release(
        "products",
        "https://www.pokemon-card.com/products/",
    )
    assert first.release_id != duplicate.release_id

    state = MonitorState.load(tmp_path / "monitor_state.json")
    state.data["seen_releases"][first.release_id] = first.__dict__
    state.data["delivery_journal"][f"release:{first.release_id}"] = {
        "status": "complete",
        "updated_at": "2026-08-08T00:52:54+00:00",
    }

    prepared, new_count = cli._prepare_releases(state, [duplicate])

    assert new_count == 0
    assert prepared[0].release_id == first.release_id
    assert state.delivered(f"release:{prepared[0].release_id}")


def test_snkrdunk_invitation_date_is_repaired_from_first_delivery(
    tmp_path,
) -> None:
    current = LotteryCase(
        "pokemon_card",
        "amazon_jp",
        "Amazon.co.jp",
        "拡張パック「30th CELEBRATION」",
        "拡張パック",
        "拡張パック「30thCELEBRATION」",
        date(2026, 8, 9),
        "https://www.amazon.co.jp/dp/B0GXCRBL5J",
        "https://snkrdunk.com/articles/32425/",
        SourceTier.SECONDARY,
        "snkrdunk_open_invitation_seen",
        "low",
    ).with_id()
    state = MonitorState.load(tmp_path / "monitor_state.json")
    state.data["seen_cases"][current.case_id] = {
        **current.__dict__,
        "start_at": "2026-08-09",
    }
    state.data["delivery_journal"][f"lottery:started:{current.case_id}"] = {
        "status": "complete",
        "updated_at": "2026-08-03T11:33:30+00:00",
    }

    prepared = cli._reuse_first_detection_start(state, current)

    assert prepared.start_at == date(2026, 8, 3)


def test_unchanged_calendar_event_is_not_updated_again(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path = tmp_path / "monitor_state.json"
    case = _lottery(date.today() + timedelta(days=1))
    calendar_calls: list[str] = []
    discord_calls: list[str] = []

    class FakeCalendar:
        def upsert(
            self,
            kind: str,
            internal_id: str,
            _summary: str,
            _when: object,
            _description: str,
            dedupe_key: str | None = None,
        ) -> dict[str, str]:
            assert kind == "lottery"
            assert dedupe_key is None
            calendar_calls.append(internal_id)
            return {"status": "inserted", "event_id": "fake"}

    class FakeDiscord:
        def send(self, title: str, _description: str) -> dict[str, str]:
            discord_calls.append(title)
            return {"status": "sent"}

    monkeypatch.setattr(
        cli,
        "run_pipeline",
        lambda *_args, **_kwargs: ([case], [], []),
    )
    monkeypatch.setattr(cli, "CalendarAdapter", FakeCalendar)
    monkeypatch.setattr(cli, "DiscordAdapter", FakeDiscord)
    state = MonitorState.load(state_path)
    state.data["baseline_complete"] = True
    state.data["armed"] = True
    state.save()
    arguments = [
        "--config",
        "sites.yaml",
        "--state",
        str(state_path),
        "run",
    ]

    assert cli.main(arguments) == 0
    assert cli.main(arguments) == 0

    assert calendar_calls == [case.case_id]
    assert discord_calls == [
        "【ポケカ抽選開始】テスト店舗／拡張パック「テスト」"
    ]


def test_atomic_save_keeps_previous_state_when_replace_fails(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "monitor_state.json"
    state = MonitorState.load(path)
    state.data["sentinel"] = "before"
    state.save()
    original = path.read_bytes()
    state.data["sentinel"] = "after"

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("simulated filesystem failure")

    monkeypatch.setattr(state_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated filesystem failure"):
        state.save()

    assert path.read_bytes() == original
    assert json.loads(path.read_text(encoding="utf-8"))["sentinel"] == "before"
    assert not path.with_name("monitor_state.json.tmp").exists()


def test_invalid_state_mapping_is_rejected_without_overwrite(tmp_path) -> None:
    path = tmp_path / "monitor_state.json"
    invalid = '{"schema_version": 1, "seen_cases": []}\n'
    path.write_text(invalid, encoding="utf-8")

    with pytest.raises(ValueError, match="seen_cases"):
        MonitorState.load(path)

    assert path.read_text(encoding="utf-8") == invalid


def test_schema_v1_state_is_upgraded_without_losing_delivery_history(
    tmp_path,
) -> None:
    path = tmp_path / "monitor_state.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "baseline_complete": True,
                "armed": True,
                "seen_cases": {"legacy": {"case_id": "legacy"}},
                "seen_releases": {},
                "ocr_cache": {},
                "delivery_journal": {
                    "lottery:started:legacy": {"status": "complete"}
                },
                "alerts": {},
            }
        ),
        encoding="utf-8",
    )

    state = MonitorState.load(path)
    state.save()
    reloaded = MonitorState.load(path)

    assert reloaded.data["schema_version"] == 2
    assert reloaded.data["seen_cases"]["legacy"]["case_id"] == "legacy"
    assert reloaded.delivered("lottery:started:legacy")
    assert reloaded.data["delivery_journal"]["lottery:started:legacy"][
        "updated_at"
    ]


def test_state_prunes_expired_resolved_alerts_ocr_and_delivery(tmp_path) -> None:
    now = datetime(2026, 7, 25, tzinfo=UTC)
    old = (now - timedelta(days=800)).isoformat()
    state = MonitorState.load(tmp_path / "monitor_state.json")
    state.data["alerts"]["resolved"] = {
        "status": "resolved",
        "resolved_at": old,
    }
    state.data["ocr_cache"]["old-post"] = "cached text"
    state.data["ocr_cache_meta"]["old-post"] = {"updated_at": old}
    state.data["ocr_pending"]["pending-post"] = {
        "last_seen_at": old,
        "attempts": 2,
    }
    state.data["delivery_journal"]["old-delivery"] = {
        "status": "complete",
        "updated_at": old,
    }
    state.data["http_cache"]["https://old.example/page"] = {
        "etag": '"old"',
        "checked_at": old,
    }

    state.prune(now)

    assert "resolved" not in state.data["alerts"]
    assert "old-post" not in state.data["ocr_cache"]
    assert "old-post" not in state.data["ocr_cache_meta"]
    assert "pending-post" not in state.data["ocr_pending"]
    assert "old-delivery" not in state.data["delivery_journal"]
    assert "https://old.example/page" not in state.data["http_cache"]


def test_state_prunes_pending_ocr_when_cache_has_recovered(tmp_path: Path) -> None:
    state = MonitorState.load(tmp_path / "monitor_state.json")
    status_url = "https://x.com/example/status/123"
    state.data["ocr_cache"][status_url] = "OCRで取得済みの本文"
    state.data["ocr_cache_meta"][status_url] = {
        "updated_at": datetime.now(UTC).isoformat()
    }
    state.data["ocr_pending"][status_url] = {
        "attempts": 1,
        "last_error": "以前のOCR失敗",
        "last_seen_at": datetime.now(UTC).isoformat(),
    }

    state.save()

    reloaded = MonitorState.load(state.path)
    assert status_url in reloaded.data["ocr_cache"]
    assert status_url not in reloaded.data["ocr_pending"]


def test_github_summary_contains_requested_counts(tmp_path) -> None:
    state = MonitorState.load(tmp_path / "monitor_state.json")
    state.data["last_run_summary"] = {
        "successful_monitors": 41,
        "degraded_monitors": 2,
        "failed_monitors": 3,
        "alerts": 2,
        "new_lotteries": 4,
        "new_releases": 1,
        "duration_ms": 1234,
    }

    summary = cli._summary_markdown(state)

    assert "| 成功監視 | 41 |" in summary
    assert "| 代替経路で継続 | 2 |" in summary
    assert "| 失敗監視 | 3 |" in summary
    assert "| 異常 | 2 |" in summary
    assert "| 新規抽選 | 4 |" in summary
    assert "| 新規発売 | 1 |" in summary
    assert "処理時間: 1.2秒" in summary


def test_failed_run_does_not_reuse_previous_http_status(tmp_path: Path) -> None:
    state = MonitorState.load(tmp_path / "monitor_state.json")
    state.record_monitor(
        "example",
        {
            "last_fetch_at": "2026-07-25T10:00:00+00:00",
            "http_status": 200,
            "fetch_method": "http",
        },
        success=True,
    )
    state.record_monitor(
        "example",
        {
            "last_fetch_at": "2026-07-26T10:00:00+00:00",
            "http_status": None,
            "fetch_method": "http",
            "last_error": "host_circuit_open",
            "failure_cause": "ConnectTimeout",
            "failure_attempts": 3,
        },
        success=False,
    )

    record = state.data["monitors"]["example"]
    assert record["http_status"] is None
    assert record["last_http_status"] == 200
    assert record["failure_cause"] == "ConnectTimeout"
    assert record["failure_attempts"] == 3
