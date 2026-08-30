from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tcg_monitor.classifier import classify_product
from tcg_monitor.config import load_config
from tcg_monitor.parsers.local_lottery import parse_livepocket_event
from tcg_monitor.parsers.lorcana_official import (
    discover_lorcana_product_urls,
    parse_lorcana_official_product,
)
from tcg_monitor.parsers.yugioh_official import parse_yugioh_official_products
from tcg_monitor.pipeline import run_pipeline


def _source(source_id: str):  # type: ignore[no-untyped-def]
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == source_id)
    return config, source


def test_yugioh_catalog_keeps_regular_and_limited_boxes_only() -> None:
    config, source = _source("yugioh_official_products")
    html = Path("tests/fixtures/yugioh_official_products.html").read_text(encoding="utf-8")

    _, releases, alerts = parse_yugioh_official_products(
        html,
        "https://www.yugioh-card.com/japan/products/",
        source,
        config,
        today=date(2026, 8, 11),
    )

    by_key = {release.canonical_product_key: release for release in releases}
    assert set(by_key) == {"immortal-phoenix", "limited-pack-wcs-2026"}
    assert by_key["immortal-phoenix"].release_date == date(2026, 10, 31)
    assert by_key["limited-pack-wcs-2026"].release_date == date(2026, 8, 29)
    assert not alerts


def test_yugioh_market_filter_is_series_specific() -> None:
    game = load_config("sites.yaml").games["yu_gi_oh"]

    assert classify_product(
        game,
        "IMMORTAL PHOENIX",
        "基本パック IMMORTAL PHOENIX",
    ).is_box
    assert classify_product(
        game,
        "REVOLUTION BOOSTER",
        "コンセプトパック REVOLUTION BOOSTER",
    ).is_box
    assert not classify_product(
        game,
        "デッキビルドパック グロリアス・ヴィクターズ",
        "コンセプトパック 1BOX",
    ).is_box
    assert not classify_product(
        game,
        "WORLD PREMIERE PACK 2026",
        "コンセプトパック 1BOX",
    ).is_box


def test_lorcana_catalog_follows_only_booster_details() -> None:
    config, source = _source("lorcana_official_products")
    root_url = "https://www.takaratomy.co.jp/products/disneylorcana/product/"
    set_url = root_url + "attack-of-the-vine/"
    detail_url = set_url + "booster-pack/"

    root = Path("tests/fixtures/lorcana_official_products.html").read_text(encoding="utf-8")
    set_page = Path("tests/fixtures/lorcana_official_products__attack-of-the-vine.html").read_text(
        encoding="utf-8"
    )
    detail = Path(
        "tests/fixtures/lorcana_official_products__attack-of-the-vine__booster_pack.html"
    ).read_text(encoding="utf-8")

    assert discover_lorcana_product_urls(root, root_url) == [set_url]
    assert discover_lorcana_product_urls(set_page, set_url) == [detail_url]
    _, releases, alerts = parse_lorcana_official_product(
        detail,
        detail_url,
        source,
        config,
        today=date(2026, 8, 11),
    )
    assert not alerts
    assert len(releases) == 1
    assert releases[0].release_date == date(2026, 7, 17)
    assert "ヴァインズ・アタック" in releases[0].product_name


def test_shared_lottery_parser_recognizes_yugioh_and_lorcana() -> None:
    config, source = _source("livepocket_hobby_station")
    start = datetime(2026, 8, 20, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    samples = (
        (
            "yu_gi_oh",
            "遊戯王OCG 基本パック「IMMORTAL PHOENIX」1BOX",
        ),
        (
            "lorcana",
            "ディズニー・ロルカナ ブースターパック「新章テスト」1BOX",
        ),
    )
    for game_id, product in samples:
        html = (
            f"<h1>{product} 抽選販売</h1><p>販売受付期間：2026年8月20日 10:00 ～ 8月23日 23:59</p>"
        )
        cases, _, alerts = parse_livepocket_event(
            html,
            f"https://livepocket.jp/e/{game_id}",
            source,
            config,
        )
        assert not alerts
        assert len(cases) == 1
        assert cases[0].game_id == game_id
        assert cases[0].start_at == start


def test_new_official_sources_run_end_to_end_with_fixtures() -> None:
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
        {"yugioh_official_products", "lorcana_official_products"},
    )

    assert {release.game_id for release in releases} == {"yu_gi_oh", "lorcana"}
    assert not alerts
