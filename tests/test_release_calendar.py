from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from google.oauth2 import service_account
from googleapiclient import discovery
from googleapiclient.errors import HttpError
from httplib2 import Response

from tcg_monitor import cli
from tcg_monitor.browser_fetch import (
    identified_browser_user_agent,
    pokemon_release_window_url,
)
from tcg_monitor.config import load_config
from tcg_monitor.google_calendar import (
    RELEASE_EVENT_COLOR_ID,
    CalendarAdapter,
    normalize_calendar_id,
)
from tcg_monitor.identity import release_dedupe_key
from tcg_monitor.japanese_datetime import parse_first_datetime
from tcg_monitor.models import Alert, LotteryCase, Release, SourceTier
from tcg_monitor.parsers.snkrdunk import discover_snkrdunk_article_urls
from tcg_monitor.pipeline import run_pipeline
from tcg_monitor.source_priority import merge_lotteries, merge_releases


def test_dotted_exact_date_is_not_month_only() -> None:
    parsed = parse_first_datetime("発売日 2026.08.22(土)")
    assert parsed.value == date(2026, 8, 22)
    assert parsed.month_only is None
    assert parse_first_datetime("発売日 2026.10").month_only == "2026-10"
    assert parse_first_datetime("受付期間 7/20(月)", date(2026, 7, 19)).value == date(2026, 7, 20)


def test_browser_user_agent_keeps_chromium_shape_and_monitor_identity() -> None:
    user_agent = identified_browser_user_agent(
        "140.0.7339.16",
        "https://github.com/nekopone/tcg-box-monitor\n",
    )

    assert user_agent.startswith("Mozilla/5.0 (X11; Linux x86_64)")
    assert "Chrome/140.0.7339.16 Safari/537.36" in user_agent
    assert "TCGBoxLotteryMonitor/2.0" in user_agent
    assert "\n" not in user_agent


def test_ocr_hour_range_end_is_not_parsed_as_minutes() -> None:
    timezone = ZoneInfo("Asia/Tokyo")
    assert parse_first_datetime(
        "2026年8月7日(金) 12時20時"
    ).value == datetime(2026, 8, 7, 12, 0, tzinfo=timezone)
    assert parse_first_datetime(
        "2026年8月7日(金) 12時30"
    ).value == datetime(2026, 8, 7, 12, 30, tzinfo=timezone)


def test_onepiece_calendar_labels_are_unambiguous() -> None:
    config = load_config("sites.yaml")
    onepiece = config.games["one_piece_card"]
    assert onepiece.release_calendar_prefix == "【ワンピ販売】"
    assert onepiece.lottery_start_prefix == "【ワンピ抽選】"


def test_official_release_fixtures() -> None:
    config = load_config("sites.yaml")
    _, releases, alerts = run_pipeline(
        config,
        "tests/fixtures",
        {"pokemon_official_products", "onepiece_official_products"},
    )
    by_key = {release.canonical_product_key: release for release in releases}
    assert by_key["OP-17"].release_date == date(2026, 8, 22)
    assert by_key["EB-05"].release_month == "2026-10"
    assert any(
        release.game_id == "pokemon_card" and release.release_date == date(2026, 7, 31)
        for release in releases
    )
    assert not any("FUTURISTIC BOX" in release.product_name for release in releases)
    assert not [alert for alert in alerts if alert.reason_code == "expected_element_missing"]


def test_pokemon_release_window_preserves_filter() -> None:
    result = pokemon_release_window_url(
        "https://www.pokemon-card.com/products/index.html?productType=expansion",
        365,
        date(2026, 7, 18),
    )
    assert "productType=expansion" in result
    assert "dateLowerY=2026" in result
    assert "dateUpperY=2027" in result


def test_live_calendar_requires_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_CALENDAR_ID", raising=False)
    with pytest.raises(RuntimeError, match="Secrets"):
        CalendarAdapter().upsert("release", "id", "title", date(2026, 8, 22), "desc")


def test_calendar_id_copy_whitespace_is_removed() -> None:
    assert normalize_calendar_id(" calendar-id@example.com\n") == "calendar-id@example.com"


def test_calendar_auth_requests_event_only_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_scopes: list[str] = []
    fake_credentials = object()
    fake_service = object()
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")

    def fake_credentials_from_info(
        _info: object,
        *,
        scopes: list[str],
    ) -> object:
        captured_scopes.extend(scopes)
        return fake_credentials

    def fake_build(
        service_name: str,
        version: str,
        *,
        credentials: object,
        cache_discovery: bool,
    ) -> object:
        assert service_name == "calendar"
        assert version == "v3"
        assert credentials is fake_credentials
        assert cache_discovery is False
        return fake_service

    monkeypatch.setattr(
        service_account.Credentials,
        "from_service_account_info",
        fake_credentials_from_info,
    )
    monkeypatch.setattr(discovery, "build", fake_build)

    assert CalendarAdapter()._service_client() is fake_service
    assert captured_scopes == ["https://www.googleapis.com/auth/calendar.events"]


def test_calendar_api_error_does_not_expose_calendar_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calendar_id = "private-calendar-identifier"
    response = Response({"status": "403"})
    error = HttpError(
        response,
        b'{"error":{"message":"forbidden"}}',
        uri=f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
    )

    class FailingRequest:
        def execute(self) -> object:
            raise error

    class FailingEvents:
        def insert(self, **_kwargs: object) -> FailingRequest:
            return FailingRequest()

    class FailingService:
        def events(self) -> FailingEvents:
            return FailingEvents()

    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
    adapter = CalendarAdapter(calendar_id=calendar_id)
    adapter._service = FailingService()

    with pytest.raises(RuntimeError) as captured:
        adapter.upsert("release", "id", "title", date(2026, 8, 22), "description")

    assert calendar_id not in str(captured.value)
    assert str(captured.value) == "Google Calendar APIエラー: status=403"


def test_release_events_are_red_and_lotteries_keep_default_color(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_bodies: list[dict[str, object]] = []

    class SuccessfulRequest:
        def execute(self) -> dict[str, object]:
            return {}

    class RecordingEvents:
        def insert(
            self,
            *,
            calendarId: str,
            body: dict[str, object],
        ) -> SuccessfulRequest:
            assert calendarId == "monitor-calendar"
            captured_bodies.append(body)
            return SuccessfulRequest()

    class RecordingService:
        def events(self) -> RecordingEvents:
            return RecordingEvents()

    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
    adapter = CalendarAdapter(calendar_id="monitor-calendar")
    adapter._service = RecordingService()

    adapter.upsert(
        "release",
        "release-id",
        "【ポケカ発売】テスト",
        date(2026, 8, 22),
        "description",
    )
    adapter.upsert(
        "lottery",
        "lottery-id",
        "【ポケカ抽選】テスト",
        date(2026, 8, 20),
        "description",
    )

    assert RELEASE_EVENT_COLOR_ID == "11"
    assert captured_bodies[0]["colorId"] == RELEASE_EVENT_COLOR_ID
    assert "colorId" not in captured_bodies[1]


def test_calendar_reconcile_confirms_an_existing_owned_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = CalendarAdapter(calendar_id="monitor-calendar")
    event_id = adapter.event_id("release", "release-id")
    body = adapter._event_body(
        event_id,
        "release",
        "release-id",
        "【遊戯王発売】テスト",
        date(2026, 9, 26),
        "description",
        "dedupe-key",
    )

    class SuccessfulRequest:
        def execute(self) -> dict[str, object]:
            return body

    class ExistingEvents:
        def get(self, **_kwargs: object) -> SuccessfulRequest:
            return SuccessfulRequest()

    class ExistingService:
        def events(self) -> ExistingEvents:
            return ExistingEvents()

    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
    adapter._service = ExistingService()

    assert adapter.reconcile(
        "release",
        "release-id",
        "【遊戯王発売】テスト",
        date(2026, 9, 26),
        "description",
        dedupe_key="dedupe-key",
        known_event_id=event_id,
    ) == {"status": "unchanged", "event_id": event_id}


def test_calendar_reconcile_recreates_a_tombstoned_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = CalendarAdapter(calendar_id="monitor-calendar")
    deterministic_id = adapter.event_id("release", "deleted-release")
    inserted_bodies: list[dict[str, object]] = []

    class ResultRequest:
        def __init__(
            self,
            result: dict[str, object] | None = None,
            error_status: int | None = None,
        ) -> None:
            self.result = result or {}
            self.error_status = error_status

        def execute(self) -> dict[str, object]:
            if self.error_status is not None:
                raise HttpError(
                    Response({"status": str(self.error_status)}),
                    b'{"error":{"message":"test"}}',
                )
            return self.result

    class RecoveringEvents:
        def get(self, **_kwargs: object) -> ResultRequest:
            return ResultRequest(error_status=410)

        def list(self, **_kwargs: object) -> ResultRequest:
            return ResultRequest({"items": []})

        def insert(
            self,
            *,
            calendarId: str,
            body: dict[str, object],
        ) -> ResultRequest:
            assert calendarId == "monitor-calendar"
            inserted_bodies.append(dict(body))
            if len(inserted_bodies) == 1:
                return ResultRequest(error_status=409)
            return ResultRequest()

    recovering_events = RecoveringEvents()

    class RecoveringService:
        def events(self) -> RecoveringEvents:
            return recovering_events

    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
    adapter._service = RecoveringService()

    result = adapter.reconcile(
        "release",
        "deleted-release",
        "【遊戯王発売】復旧テスト",
        date(2026, 9, 26),
        "description",
        known_event_id=deterministic_id,
    )

    assert result["status"] == "inserted"
    assert result["event_id"] != deterministic_id
    assert inserted_bodies[0]["id"] == deterministic_id
    assert inserted_bodies[1]["id"] == result["event_id"]
    assert inserted_bodies[1]["colorId"] == RELEASE_EVENT_COLOR_ID


def test_release_color_changes_only_the_release_sync_hash() -> None:
    plain_hash = cli._calendar_payload_hash(
        "【ポケカ抽選】テスト",
        date(2026, 8, 20),
        "description",
    )
    assert plain_hash == cli._calendar_payload_hash(
        "【ポケカ抽選】テスト",
        date(2026, 8, 20),
        "description",
        color_id=None,
    )
    assert plain_hash != cli._calendar_payload_hash(
        "【ポケカ抽選】テスト",
        date(2026, 8, 20),
        "description",
        color_id=RELEASE_EVENT_COLOR_ID,
    )


def test_existing_release_color_update_verifies_ownership_and_patches_only_color(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_patches: list[dict[str, object]] = []
    owned_event: dict[str, object] = {
        "extendedProperties": {
            "private": {
                "kind": "release",
                "internal_id": "historical-release",
            }
        }
    }

    class SuccessfulRequest:
        def __init__(self, result: dict[str, object]) -> None:
            self.result = result

        def execute(self) -> dict[str, object]:
            return self.result

    class RecordingEvents:
        def get(
            self,
            *,
            calendarId: str,
            eventId: str,
        ) -> SuccessfulRequest:
            assert calendarId == "monitor-calendar"
            assert eventId == "historical-event"
            return SuccessfulRequest(owned_event)

        def patch(
            self,
            *,
            calendarId: str,
            eventId: str,
            body: dict[str, object],
        ) -> SuccessfulRequest:
            assert calendarId == "monitor-calendar"
            assert eventId == "historical-event"
            captured_patches.append(body)
            return SuccessfulRequest({})

    recording_events = RecordingEvents()

    class RecordingService:
        def events(self) -> RecordingEvents:
            return recording_events

    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
    adapter = CalendarAdapter(calendar_id="monitor-calendar")
    adapter._service = RecordingService()

    result = adapter.set_owned_event_color(
        "historical-event",
        kind="release",
        internal_id="historical-release",
        color_id=RELEASE_EVENT_COLOR_ID,
    )

    assert result["status"] == "updated"
    assert captured_patches == [{"colorId": RELEASE_EVENT_COLOR_ID}]


def test_existing_release_color_migration_includes_past_and_runs_once(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    state_path = tmp_path / "state.json"
    state = cli.MonitorState.load(state_path)
    state.data["calendar_sync"] = {
        "release:historical-release": {
            "event_id": "historical-event",
            "payload_hash": "old-release-hash",
        },
        "lottery:existing-lottery": {
            "event_id": "lottery-event",
            "payload_hash": "lottery-hash",
        },
    }
    calls: list[tuple[str, str, str, str]] = []

    class FakeCalendar:
        def set_owned_event_color(
            self,
            event_id: str,
            *,
            kind: str,
            internal_id: str,
            color_id: str,
        ) -> dict[str, str]:
            calls.append((event_id, kind, internal_id, color_id))
            return {"status": "updated", "event_id": event_id}

    first = cli._migrate_existing_release_event_colors(state, FakeCalendar())
    second = cli._migrate_existing_release_event_colors(state, FakeCalendar())

    assert first == [{"status": "updated"}]
    assert second == []
    assert calls == [
        (
            "historical-event",
            "release",
            "historical-release",
            RELEASE_EVENT_COLOR_ID,
        )
    ]
    assert state.data["release_event_color_id"] == RELEASE_EVENT_COLOR_ID


def _release(
    game_id: str,
    name: str,
    key: str,
    tier: SourceTier,
    release_date: date = date(2026, 7, 31),
) -> Release:
    return Release(
        game_id,
        name,
        "BOX",
        key,
        release_date,
        None,
        "https://official.example/product",
        "https://source.example/article",
        tier,
        "test",
        "high" if tier == SourceTier.OFFICIAL else "medium",
    ).with_id()


def test_release_merge_deduplicates_official_and_secondary_titles() -> None:
    pokemon_official = _release(
        "pokemon_card",
        "拡張パック「ストームエメラルダ」",
        "official-product-slug",
        SourceTier.OFFICIAL,
    )
    pokemon_secondary = _release(
        "pokemon_card",
        "7月31日発売：拡張パック『ストームエメラルダ』",
        "15950",
        SourceTier.SECONDARY,
    )
    onepiece_official = _release(
        "one_piece_card",
        "ブースターパック 世界最強の戦士 [OP-17]",
        "OP-17",
        SourceTier.OFFICIAL,
        date(2026, 8, 22),
    )
    onepiece_secondary = _release(
        "one_piece_card",
        "8月22日 ブースターパック「世界最強の戦士」",
        "14006",
        SourceTier.SECONDARY,
        date(2026, 8, 22),
    )
    merged, alerts = merge_releases(
        [pokemon_secondary, pokemon_official, onepiece_secondary, onepiece_official]
    )
    assert len(merged) == 2
    assert all(item.source_tier == SourceTier.OFFICIAL for item in merged)
    assert not alerts
    assert release_dedupe_key(pokemon_official) == release_dedupe_key(pokemon_secondary)
    assert release_dedupe_key(onepiece_official) == release_dedupe_key(onepiece_secondary)


def test_lottery_merge_deduplicates_livepocket_and_x_date_precision() -> None:
    common = dict(
        game_id="pokemon_card",
        retailer_id="fullcomp",
        retailer_name="フルコンプ",
        product_name="拡張パック「ストームエメラルダ」",
        product_category="拡張パック",
        canonical_product_key="ストームエメラルダ",
        official_url="https://livepocket.jp/e/example",
        source_tier=SourceTier.OFFICIAL_INDIRECT,
        confidence="high",
    )
    livepocket = LotteryCase(
        **common,
        start_at=datetime(2026, 7, 20, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        source_url="https://livepocket.jp/e/example",
        extraction_method="livepocket_detail_application_period",
    ).with_id()
    x_post = LotteryCase(
        **common,
        start_at=date(2026, 7, 20),
        source_url="https://x.com/fc_sendaieki/status/1",
        extraction_method="yahoo_realtime_body_application_period",
    ).with_id()
    merged, alerts = merge_lotteries([livepocket, x_post])
    assert len(merged) == 1
    assert not alerts


def test_snkrdunk_retailer_dates_are_parsed_and_merged() -> None:
    config = load_config("sites.yaml")
    cases, releases, alerts = run_pipeline(
        config,
        "tests/fixtures",
        {"snkrdunk_pokemon", "snkrdunk_onepiece"},
    )
    starts = {(case.retailer_id, case.start_at) for case in cases}
    assert (
        "pokemon_center_store",
        datetime(2026, 7, 22, 14, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
    ) in starts
    assert (
        "geo",
        datetime(2026, 7, 13, 11, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
    ) in starts
    assert (
        "rakuten_books",
        datetime(2026, 7, 13, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
    ) in starts
    assert (
        "hobby_search",
        datetime(2026, 8, 12, 18, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
    ) in starts
    assert len(releases) == 2
    assert not [
        alert
        for alert in alerts
        if alert.reason_code
        in {"start_time_not_published", "retailer_lottery_block_without_start"}
    ]


def test_snkrdunk_schedule_discovers_new_product_articles() -> None:
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == "snkrdunk_pokemon")
    html = """
    <h1>【ポケカ】2026年の新弾発売スケジュールまとめ</h1>
    <a href="/articles/32581/">【ポケカ】ストームエメラルダの予約・抽選情報まとめ</a>
    <a href="/articles/32650/">【ポケカ】30th CELEBRATIONの予約・抽選情報まとめ</a>
    <a href="/articles/32892/">【ポケカ】ストームエメラルダの再販はいつ？再販入荷情報まとめ</a>
    <a href="/articles/32700/">【ポケカ】スターターセットの予約・抽選情報まとめ</a>
    <a href="/articles/32800/">【ポケカ】相場・当たりランキング</a>
    """
    assert discover_snkrdunk_article_urls(html, "https://snkrdunk.com/articles/15950/", source) == [
        "https://snkrdunk.com/articles/32892/",
        "https://snkrdunk.com/articles/32650/",
        "https://snkrdunk.com/articles/32581/",
    ]


def test_run_records_expired_lottery_but_delivers_only_in_window(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def lottery(start: date) -> LotteryCase:
        return LotteryCase(
            "pokemon_card",
            "geo",
            "ゲオ",
            "拡張パック「テスト」",
            "拡張パック",
            "テスト",
            start,
            "https://geo-online.co.jp/news/test",
            "https://snkrdunk.com/articles/test/",
            SourceTier.SECONDARY,
            "test",
            "medium",
        ).with_id()

    tokyo_today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    expired = lottery(tokyo_today - timedelta(days=2))
    future = lottery(tokyo_today + timedelta(days=5))
    calendar_calls: list[str] = []
    discord_calls: list[str] = []

    class FakeCalendar:
        def upsert(
            self,
            kind: str,
            internal_id: str,
            summary: str,
            when: date,
            description: str,
            dedupe_key: str | None = None,
        ) -> dict[str, str]:
            assert kind == "lottery"
            assert "ゲオ／" in summary
            assert "公式応募ページ" in description
            calendar_calls.append(internal_id)
            return {"status": "inserted", "event_id": "fake"}

    class FakeDiscord:
        def send(self, title: str, _description: str) -> dict[str, str]:
            discord_calls.append(title)
            return {"status": "sent"}

    monkeypatch.setattr(cli, "run_pipeline", lambda *_args, **_kwargs: ([expired, future], [], []))
    monkeypatch.setattr(cli, "CalendarAdapter", FakeCalendar)
    monkeypatch.setattr(cli, "DiscordAdapter", FakeDiscord)
    state_path = tmp_path / "state.json"
    state = cli.MonitorState.load(state_path)
    state.mark_baseline()
    state.arm()
    assert cli.main(["--config", "sites.yaml", "--state", str(state_path), "run"]) == 0
    saved = json.loads(state_path.read_text())
    assert calendar_calls == [future.case_id]
    assert len(discord_calls) == 1
    assert set(saved["seen_cases"]) == {expired.case_id, future.case_id}


def test_run_corrects_existing_calendar_without_duplicate_discord(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def lottery(product_name: str) -> LotteryCase:
        return LotteryCase(
            "pokemon_card",
            "yorozuya_morioka",
            "萬屋盛岡店",
            product_name,
            "BOX（投稿記載から推定）",
            product_name,
            date.today(),
            "https://x.com/yorozuya_card/status/2079755316506599865",
            "https://x.com/yorozuya_card/status/2079755316506599865",
            SourceTier.OFFICIAL_INDIRECT,
            "yahoo_realtime_detected_open",
            "low",
            "stable-status-id",
        )

    old = lottery("抽選 販売について")
    corrected = lottery("ストームエメラルダ")
    calendar_summaries: list[str] = []
    discord_calls: list[str] = []

    class FakeCalendar:
        def upsert(
            self,
            _kind: str,
            _internal_id: str,
            summary: str,
            _when: date,
            _description: str,
        ) -> dict[str, str]:
            calendar_summaries.append(summary)
            return {"status": "updated", "event_id": "fake"}

    class FakeDiscord:
        def send(self, title: str, _description: str) -> dict[str, str]:
            discord_calls.append(title)
            return {"status": "sent"}

    monkeypatch.setattr(cli, "run_pipeline", lambda *_args, **_kwargs: ([corrected], [], []))
    monkeypatch.setattr(cli, "CalendarAdapter", FakeCalendar)
    monkeypatch.setattr(cli, "DiscordAdapter", FakeDiscord)
    state_path = tmp_path / "state.json"
    state = cli.MonitorState.load(state_path)
    state.mark_baseline()
    state.arm()
    state.data["seen_cases"][old.case_id] = old.__dict__
    state.mark_delivered(f"lottery:started:{old.case_id}")

    assert cli.main(["--config", "sites.yaml", "--state", str(state_path), "run"]) == 0
    saved = json.loads(state_path.read_text())
    assert calendar_summaries == ["【ポケカ抽選開始】萬屋盛岡店／ストームエメラルダ"]
    assert not discord_calls
    assert saved["seen_cases"][old.case_id]["product_name"] == "ストームエメラルダ"


def test_run_updates_existing_calendar_when_correction_moves_start_to_past(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status_url = "https://x.com/GEO_official/status/2072968946731594147"

    def lottery(product_name: str, start: date) -> LotteryCase:
        return LotteryCase(
            "pokemon_card",
            "geo",
            "ゲオ",
            product_name,
            "拡張パック",
            product_name,
            start,
            status_url,
            status_url,
            SourceTier.OFFICIAL_INDIRECT,
            "yahoo_realtime_image_ocr_application_period",
            "medium",
        ).with_id()

    old = lottery("拡張パック「対象商品」", date.today())
    corrected_start = date.today() - timedelta(days=12)
    corrected = lottery("拡張パック「ストームエメラルダ」", corrected_start)
    calendar_calls: list[tuple[str, date]] = []
    discord_calls: list[str] = []

    class FakeCalendar:
        def upsert(
            self,
            _kind: str,
            internal_id: str,
            _summary: str,
            when: date,
            _description: str,
        ) -> dict[str, str]:
            calendar_calls.append((internal_id, when))
            return {"status": "updated", "event_id": "fake"}

    class FakeDiscord:
        def send(self, title: str, _description: str) -> dict[str, str]:
            discord_calls.append(title)
            return {"status": "sent"}

    monkeypatch.setattr(cli, "run_pipeline", lambda *_args, **_kwargs: ([corrected], [], []))
    monkeypatch.setattr(cli, "CalendarAdapter", FakeCalendar)
    monkeypatch.setattr(cli, "DiscordAdapter", FakeDiscord)
    state_path = tmp_path / "state.json"
    state = cli.MonitorState.load(state_path)
    state.mark_baseline()
    state.arm()
    state.data["seen_cases"][old.case_id] = old.__dict__
    state.mark_delivered(f"lottery:started:{old.case_id}")
    state.mark_calendar_synced(
        f"lottery:{old.case_id}",
        "old-payload",
        {"status": "inserted", "event_id": "fake"},
    )

    assert cli.main(["--config", "sites.yaml", "--state", str(state_path), "run"]) == 0

    assert calendar_calls == [(old.case_id, corrected_start)]
    assert not discord_calls


def test_run_delivers_parser_alert_once_and_realerts_after_recovery(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    alert = Alert(
        "pokemon_card",
        "yahoo_realtime_yorozuya_morioka",
        "https://x.com/yorozuya_card/status/1",
        "萬屋盛岡店",
        ["抽選"],
        "yahoo_lottery_post_without_game",
        "本文・画像からゲームを判定できません",
        None,
        "https://x.com/yorozuya_card/status/1",
    ).with_fingerprint()
    discord_calls: list[str] = []

    class FakeCalendar:
        pass

    class FakeDiscord:
        def send(self, title: str, _description: str) -> dict[str, str]:
            discord_calls.append(title)
            return {"status": "sent"}

    current_alerts = [alert]
    monkeypatch.setattr(
        cli,
        "run_pipeline",
        lambda *_args, **_kwargs: ([], [], current_alerts),
    )
    monkeypatch.setattr(cli, "CalendarAdapter", FakeCalendar)
    monkeypatch.setattr(cli, "DiscordAdapter", FakeDiscord)
    state_path = tmp_path / "state.json"
    state = cli.MonitorState.load(state_path)
    state.mark_baseline()
    state.arm()

    args = ["--config", "sites.yaml", "--state", str(state_path), "run"]
    assert cli.main(args) == 0
    assert cli.main(args) == 0
    assert discord_calls == ["【監視異常まとめ】1件"]

    current_alerts.clear()
    assert cli.main(args) == 0
    saved = json.loads(state_path.read_text())
    assert saved["alerts"][alert.fingerprint]["status"] == "active"
    assert saved["alerts"][alert.fingerprint]["missing_runs"] == 1

    assert cli.main(args) == 0
    saved = json.loads(state_path.read_text())
    assert saved["alerts"][alert.fingerprint]["status"] == "resolved"

    current_alerts.append(alert)
    assert cli.main(args) == 0
    assert discord_calls == ["【監視異常まとめ】1件", "【監視異常まとめ】1件"]


def test_baseline_imports_future_official_release(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    release = Release(
        "pokemon_card",
        "拡張パック テスト",
        "拡張パック",
        "test-product",
        date.today() + timedelta(days=10),
        None,
        "https://www.pokemon-card.com/products/test.html",
        "https://www.pokemon-card.com/products/",
        SourceTier.OFFICIAL,
        "test",
        "high",
    ).with_id()
    calls: list[tuple[str, date]] = []

    class FakeCalendar:
        def upsert(
            self,
            kind: str,
            internal_id: str,
            summary: str,
            when: date,
            description: str,
            dedupe_key: str | None = None,
        ) -> dict[str, str]:
            assert kind == "release"
            assert internal_id == release.release_id
            assert "公式商品ページ" in description
            assert dedupe_key
            calls.append((summary, when))
            return {"status": "inserted", "event_id": "fake"}

    monkeypatch.setattr(cli, "run_pipeline", lambda *_args, **_kwargs: ([], [release], []))
    monkeypatch.setattr(cli, "CalendarAdapter", FakeCalendar)
    state_path = tmp_path / "state.json"
    result = cli.main(
        [
            "--config",
            "sites.yaml",
            "--state",
            str(state_path),
            "baseline",
            "--include-future-releases",
        ]
    )
    state = json.loads(state_path.read_text())
    assert result == 0
    assert calls
    assert f"release:{release.release_id}" in state["delivery_journal"]


def test_run_reconciles_a_future_release_even_when_state_says_synced(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    release = Release(
        "yu_gi_oh",
        "ORIGINAL ARTWORK COLLECTION",
        "ORIGINAL ARTWORK COLLECTION",
        "yac1",
        date.today() + timedelta(days=10),
        None,
        "https://www.yugioh-card.com/japan/products/yac1/",
        "https://www.yugioh-card.com/japan/products/",
        SourceTier.OFFICIAL,
        "official_yugioh_exact_release",
        "high",
    ).with_id()
    event_id = "known-calendar-event"
    reconcile_calls: list[str | None] = []
    discord_calls: list[str] = []

    class FakeCalendar:
        def reconcile(
            self,
            kind: str,
            internal_id: str,
            _summary: str,
            _when: date,
            _description: str,
            dedupe_key: str | None = None,
            known_event_id: str | None = None,
        ) -> dict[str, str]:
            assert kind == "release"
            assert internal_id == release.release_id
            assert dedupe_key
            reconcile_calls.append(known_event_id)
            return {"status": "unchanged", "event_id": event_id}

    class FakeDiscord:
        def send(self, title: str, _description: str) -> dict[str, str]:
            discord_calls.append(title)
            return {"status": "sent"}

    monkeypatch.setattr(cli, "run_pipeline", lambda *_args, **_kwargs: ([], [release], []))
    monkeypatch.setattr(cli, "CalendarAdapter", FakeCalendar)
    monkeypatch.setattr(cli, "DiscordAdapter", FakeDiscord)
    state_path = tmp_path / "state.json"
    state = cli.MonitorState.load(state_path)
    state.mark_baseline()
    state.arm()
    state.data["release_event_color_id"] = RELEASE_EVENT_COLOR_ID
    state.data["seen_releases"][release.release_id] = release.__dict__
    key = f"release:{release.release_id}"
    state.mark_delivered(key)
    summary = "【遊戯王発売】" + release.product_name
    description = cli._release_description(
        release,
        datetime.now(ZoneInfo("Asia/Tokyo")),
    )
    payload_hash = cli._calendar_payload_hash(
        summary,
        release.release_date,
        description,
        release_dedupe_key(release),
        color_id=RELEASE_EVENT_COLOR_ID,
    )
    state.mark_calendar_synced(
        key,
        payload_hash,
        {"status": "inserted", "event_id": event_id},
    )

    assert cli.main(["--config", "sites.yaml", "--state", str(state_path), "run"]) == 0
    assert reconcile_calls == [event_id]
    assert not discord_calls
