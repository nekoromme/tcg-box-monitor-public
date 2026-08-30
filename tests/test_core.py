from datetime import datetime
from pathlib import Path

import pytest

from tcg_monitor.classifier import classify_product
from tcg_monitor.config import ConfigError, load_config
from tcg_monitor.google_calendar import CalendarAdapter
from tcg_monitor.japanese_datetime import parse_first_datetime
from tcg_monitor.models import Alert, LotteryStartPolicy
from tcg_monitor.pipeline import _collapse_provider_http_alerts, run_pipeline
from tcg_monitor.state import MonitorState


def test_config():
    c = load_config("sites.yaml")
    assert c.schema_version == 2
    assert "pokemon_card" in c.games
    sanuma = next(source for source in c.sources if source.id == "yahoo_realtime_tsutaya_sanuma")
    assert sanuma.lottery_start_policy == LotteryStartPolicy.FIRST_DETECTION_NEXT_DAY


def test_monitoring_policy_uses_one_interval_and_all_six_games() -> None:
    config = load_config("sites.yaml")
    required_games = {
        "pokemon_card",
        "one_piece_card",
        "dragon_ball_fusion_world",
        "lorcana",
        "yu_gi_oh",
        "gundam_card",
    }
    uniform_minutes = config.system["uniform_source_poll_minutes"]

    assert uniform_minutes == 120
    assert set(config.system["general_retail_required_game_ids"]) == required_games
    assert all(source.poll_minutes == uniform_minutes for source in config.sources)

    general_retailer = next(source for source in config.sources if source.id == "geo")
    assert required_games <= general_retailer.parse_game_ids

    specialized = next(source for source in config.sources if source.id == "pokemon_center_online")
    assert "pokemon_card" in specialized.parse_game_ids
    assert "yu_gi_oh" not in specialized.parse_game_ids


def test_bad_lottery_start_policy_is_rejected(tmp_path: Path) -> None:
    config_text = Path("sites.yaml").read_text(encoding="utf-8")
    bad_config = config_text.replace(
        "lottery_start_policy: first_detection_next_day",
        "lottery_start_policy: winner_announcement",
    )
    config_path = tmp_path / "sites.yaml"
    config_path.write_text(bad_config, encoding="utf-8")

    with pytest.raises(
        ConfigError,
        match="bad lottery_start_policy: yahoo_realtime_tsutaya_sanuma",
    ):
        load_config(config_path)


def test_datetime():
    r = parse_first_datetime("2026年7月20日(月) 午後1時05分")
    assert isinstance(r.value, datetime)
    assert r.value.hour == 13
    assert parse_first_datetime("2026年7月20日(火)").warnings == ("weekday_date_mismatch",)
    assert parse_first_datetime("2026.10").month_only == "2026-10"


def test_datetime_uses_earliest_match_across_time_formats():
    parsed = parse_first_datetime("公開 2026年07月15日 12:05 受付締切 7月22日 23時59分まで")
    assert parsed.value == datetime.fromisoformat("2026-07-15T12:05:00+09:00")


def test_classifier():
    c = load_config("sites.yaml")
    g = c.games["pokemon_card"]
    assert classify_product(g, "拡張パック X", "1BOX=30パック").is_box
    assert not classify_product(g, "スターターセット", "1BOX").is_box


def test_pipeline_fixtures():
    c = load_config("sites.yaml")
    cases, releases, alerts = run_pipeline(
        c,
        "tests/fixtures",
        {"pokemon_official_products", "onepiece_official_products", "geo", "snkrdunk_pokemon"},
    )
    assert any(r.game_id == "pokemon_card" for r in releases)
    assert any(r.canonical_product_key == "OP-17" for r in releases)
    assert any(r.release_month == "2026-10" for r in releases)
    assert any(x.case_id for x in cases)


def test_ids_calendar_state(tmp_path):
    eid = CalendarAdapter(dry_run=True).event_id("release", "abc")
    assert eid.startswith("tcg")
    st = MonitorState.load(tmp_path / "s.json")
    st.mark_baseline()
    st.arm()
    st.mark_delivered("k")
    assert st.delivered("k")


def test_provider_http_failures_are_collapsed_across_accounts() -> None:
    alerts = [
        Alert(
            None,
            f"source-{index}",
            f"https://twstalker.com/account-{index}",
            f"account-{index}",
            [],
            "repeated_http_error",
            "HTTPエラー",
            429,
            f"https://twstalker.com/account-{index}",
        ).with_fingerprint()
        for index in range(3)
    ]
    collapsed = _collapse_provider_http_alerts(alerts)
    assert len(collapsed) == 1
    assert collapsed[0].source_id == "provider:twstalker.com"
    assert collapsed[0].http_status == 429
