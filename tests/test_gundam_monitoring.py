from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tcg_monitor.classifier import classify_product
from tcg_monitor.config import load_config
from tcg_monitor.parsers.gundam_official import parse_gundam_official_products
from tcg_monitor.parsers.local_lottery import parse_livepocket_event
from tcg_monitor.pipeline import run_pipeline


def _source(source_id: str):  # type: ignore[no-untyped-def]
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == source_id)
    return config, source


def test_gundam_official_catalog_parses_future_booster_dates() -> None:
    config, source = _source("gundam_official_products")
    html = Path("tests/fixtures/gundam_official_products.html").read_text(encoding="utf-8")

    _, releases, alerts = parse_gundam_official_products(
        html,
        source.discovery_urls[0],
        source,
        config,
        today=date(2026, 8, 30),
    )

    by_key = {release.canonical_product_key: release for release in releases}
    assert set(by_key) == {"GD06", "GD07"}
    assert by_key["GD06"].release_date == date(2026, 10, 31)
    assert by_key["GD07"].release_date == date(2027, 1, 30)
    assert by_key["GD07"].official_url.endswith("/jp/products/gd07.html")
    assert not alerts


def test_gundam_box_classifier_uses_product_codes_and_excludes_decks() -> None:
    game = load_config("sites.yaml").games["gundam_card"]

    booster = classify_product(game, "Stardust Trails [GD06]", "ブースター")
    starter = classify_product(game, "スタートデッキ [ST09]", "1BOX")

    assert booster.is_box
    assert booster.canonical_product_key == "GD06"
    assert not starter.is_box


def test_shared_lottery_parser_recognizes_gundam_box() -> None:
    config, source = _source("livepocket_hobby_station")
    html = (
        "<h1>ガンダムカードゲーム ブースターパック「Stardust Trails」[GD06] 1BOX 抽選販売</h1>"
        "<p>販売受付期間：2026年9月1日 10:00 ～ 9月3日 23:59</p>"
    )

    cases, _, alerts = parse_livepocket_event(
        html,
        "https://livepocket.jp/e/gundam-card",
        source,
        config,
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].game_id == "gundam_card"
    assert cases[0].canonical_product_key == "GD06"
    assert cases[0].start_at == datetime(
        2026,
        9,
        1,
        10,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )


def test_gundam_official_source_runs_end_to_end_with_fixture() -> None:
    config = load_config("sites.yaml")
    config = replace(
        config,
        system={
            **config.system,
            "implausible_past_days": 5_000,
            "max_future_days": 5_000,
        },
    )

    _, releases, alerts = run_pipeline(
        config,
        "tests/fixtures",
        {"gundam_official_products"},
    )

    assert {release.canonical_product_key for release in releases} == {"GD06", "GD07"}
    assert not alerts
