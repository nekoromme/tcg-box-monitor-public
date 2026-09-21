"""追加商品が実際の取得経路を通り、既存BOXと混同しないことを検証する。"""

from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from tcg_monitor.additional_products import additional_matches
from tcg_monitor.classifier import classify_product
from tcg_monitor.config import ConfigError, _additional_products, load_config
from tcg_monitor.identity import lottery_dedupe_key
from tcg_monitor.parsers.furuichi import (
    discover_furuichi_lottery_urls,
    parse_furuichi_lottery_detail,
)
from tcg_monitor.parsers.generic import discover_geo_news_urls, parse_generic
from tcg_monitor.parsers.local_lottery import _box_products, parse_yahoo_realtime
from tcg_monitor.parsers.pokemon_center import parse_pokemon_center_lottery
from tcg_monitor.parsers.retailer_lottery import (
    discover_retailer_lottery_urls,
    parse_retailer_lottery_detail,
)
from tcg_monitor.source_priority import merge_lotteries

FAMILY = "30th CELEBRATION カードセット"
CONFIG = load_config("sites.yaml")
GAME = CONFIG.games["pokemon_card"]
VARIANTS = GAME.additional_products[0].variants
PERIOD = "応募受付期間 2026年9月21日10:00～2026年9月25日23:59"


def source(source_id):  # type: ignore[no-untyped-def]
    return next(s for s in CONFIG.sources if s.id == source_id)


@pytest.mark.parametrize("variant", VARIANTS)
def test_all_nine_are_targets_but_not_boxes(variant: str) -> None:
    name = f"ポケモンカードゲーム MEGA「{FAMILY} {variant}」"
    item = classify_product(GAME, name, name)
    assert item.is_target and not item.is_box
    assert item.product_name == f"{FAMILY} {variant}"
    assert item.canonical_product_key.startswith("pokemon_30th_cardset:")


@pytest.mark.parametrize(
    "name",
    [
        "30thカードセット",
        "３０ｔｈ ＣＥＬＥＢＲＡＴＩＯＮ カードセット",
        "3 0 t h C E L E B R A T I O N カ ー ド セ ッ ト",
    ],
)
def test_aliases_and_ocr_spacing(name: str) -> None:
    assert additional_matches(GAME, name)[0].product_name == FAMILY


def test_opt_out_and_variant_selection() -> None:
    rule = GAME.additional_products[0]
    off = replace(GAME, additional_products=(replace(rule, enabled=False),))
    assert not classify_product(off, FAMILY, FAMILY).is_target
    one = replace(GAME, additional_products=(replace(rule, selected_variants=(VARIANTS[0],)),))
    assert not additional_matches(one, FAMILY + VARIANTS[1])
    assert not additional_matches(one, FAMILY)  # 種類不明を勝手に選択種類にしない。
    assert len(additional_matches(one, FAMILY + " ".join(VARIANTS))) == 1


@pytest.mark.parametrize(
    "name",
    [
        "プレミアムデッキセット エーフィ・ブラッキー",
        "別のカードセット",
        "30th CELEBRATION デッキシールド",
        "ポケモンセンターセット",
    ],
)
def test_unselected_products_remain_excluded(name: str) -> None:
    assert not classify_product(GAME, name, name + " 1BOX").is_target


def test_mixed_contents_does_not_create_a_booster_lottery() -> None:
    text = FAMILY + "\n内容物：拡張パック「30th CELEBRATION」2パック\n" + PERIOD
    products = _box_products(text, "pokemon_card", CONFIG)
    assert [p[0] for p in products] == [FAMILY]
    mixed = text + "\n抽選商品：拡張パック「ストームエメラルダ」1BOX"
    products = _box_products(mixed, "pokemon_card", CONFIG)
    assert {p[0] for p in products} == {FAMILY, "拡張パック「ストームエメラルダ」"}


@freeze_time("2026-09-21")
def test_geo_discovery_and_detail() -> None:
    src = source("geo")
    index = f'<a href="/news/999">{FAMILY} 抽選販売</a>'
    urls = discover_geo_news_urls(index, "https://geo-online.co.jp/news/", src, CONFIG)
    assert urls == ["https://geo-online.co.jp/news/999"]
    html = f"<article><h1>{FAMILY}</h1><p>抽選販売 {PERIOD}</p></article>"
    cases, _, alerts = parse_generic(html, urls[0], src, CONFIG)
    assert not alerts and len(cases) == 1
    assert cases[0].product_name == FAMILY


@freeze_time("2026-09-21")
def test_generic_separate_html_nodes_keep_application_period() -> None:
    html = (
        f"<title>{FAMILY} 抽選</title><main><h1>{FAMILY}</h1>"
        "<div>内容物：拡張パック「30th CELEBRATION」2パック</div>"
        f"<div>抽選販売 {PERIOD}</div></main>"
    )
    cases, releases, alerts = parse_generic(
        html, "https://example.com/lottery", source("geo"), CONFIG
    )
    assert not alerts and not releases
    assert len(cases) == 1 and cases[0].product_name == FAMILY


@freeze_time("2026-09-21")
def test_furuichi_image_led_mixed_notice() -> None:
    src = source("furuichi_official_lottery")
    index = f'<a href="/news/news_information/cards0921">ポケカ {FAMILY} 抽選</a>'
    urls = discover_furuichi_lottery_urls(index, "https://www.furu1.net", src, CONFIG)
    assert len(urls) == 1
    html = (
        "<main><h2>ポケモンカードゲーム 抽選受付について</h2>"
        '<img src="/storage/news/news_information/cards0921/image.jpg"></main>'
    )
    ocr = (
        f"ポケモンカードゲーム MEGA {FAMILY} {VARIANTS[0]}\n"
        "ポケモンカードゲーム プレミアムデッキセット エーフィ・ブラッキー\n"
        f"抽選{PERIOD}"
    )
    cases, _, alerts = parse_furuichi_lottery_detail(
        html,
        urls[0],
        src,
        CONFIG,
        detected_on=date(2026, 9, 21),
        ocr_reader=lambda _: ocr,
    )
    assert not alerts
    assert len(cases) == 1 and cases[0].product_name == f"{FAMILY} {VARIANTS[0]}"


def social_html(text: str, account: str) -> str:
    # Xの投稿時刻から逆算したテスト専用の投稿番号。
    posted = datetime(2026, 9, 21, 10, tzinfo=ZoneInfo("Asia/Tokyo"))
    status = (int(posted.timestamp() * 1000) - 1288834974657) << 22
    return (
        f'<div class="Tweet_TweetContainer__test"><p class="Tweet_body__test">{text}</p>'
        f'<time><a href="https://x.com/{account}/status/{status}">9月21日</a></time></div>'
    )


@pytest.mark.parametrize(
    "source_id", ["yahoo_realtime_dmm_tsuhan", "yahoo_realtime_seagull_common"]
)
def test_social_group_or_variants_with_strict_exclusions(source_id: str) -> None:
    src = source(source_id)
    src = replace(src, parser_options={**src.parser_options, "strict_product_exclusions": True})
    text = f"{FAMILY} {VARIANTS[0]} / {VARIANTS[8]} 抽選販売 {PERIOD}"
    html = social_html(text, src.parser_options["account"])
    cases, _, alerts = parse_yahoo_realtime(
        html,
        src.discovery_urls[0],
        src,
        CONFIG,
        date(2026, 9, 21),
        known_releases=[],
    )
    assert not alerts
    assert {c.product_name for c in cases} == {f"{FAMILY} {VARIANTS[0]}", f"{FAMILY} {VARIANTS[8]}"}
    assert len({lottery_dedupe_key(c) for c in cases}) == 2
    assert len(merge_lotteries(cases + cases)) == 2


@freeze_time("2026-09-21")
def test_pokemon_center_keeps_set_and_box_distinct() -> None:
    text = (
        f"ポケモンカードゲーム MEGA {FAMILY} 抽選販売\n"
        "内容物：拡張パック「30th CELEBRATION」2パック\n" + PERIOD
    )
    cases, _, alerts = parse_pokemon_center_lottery(
        f"<main>{text}</main>",
        "https://www.pokemoncenter-online.com/news?id=999",
        source("pokemon_center_online"),
        CONFIG,
    )
    assert not alerts and len(cases) == 1
    assert cases[0].product_name == FAMILY


@freeze_time("2026-09-21")
def test_retailer_index_and_product() -> None:
    src = source("hobby_search_lottery")
    url = "https://www.1999.co.jp/99999999"
    label = f"ポケモンカードゲーム {FAMILY} {VARIANTS[0]}"
    html = f'<a href="{url}">{label} 抽選販売</a>'
    assert discover_retailer_lottery_urls(html, src.discovery_urls[0], src, CONFIG) == [url]
    detail = f"<title>{label}</title><main>{label} 抽選に応募する {PERIOD}</main>"
    cases, _, alerts = parse_retailer_lottery_detail(detail, url, src, CONFIG)
    assert not alerts and len(cases) == 1
    assert cases[0].product_name == f"{FAMILY} {VARIANTS[0]}"


@pytest.mark.parametrize(
    "raw",
    [
        None,
        {},
        [{"id": "x"}],
        [
            {"id": "x", "name": "商品", "category": "セット", "enabled": "false"},
        ],
        [
            {"id": "x", "name": "商品", "category": "セット", "selected_variants": ["不明"]},
        ],
    ],
)
def test_invalid_configuration_fails_loudly(raw: object) -> None:
    with pytest.raises(ConfigError):
        _additional_products(raw)


@freeze_time("2026-09-26")
def test_finished_lotteries_do_not_reappear_when_enabling() -> None:
    html = f"<title>{FAMILY} 抽選</title><main>ポケモンカードゲーム {FAMILY} 抽選 {PERIOD}</main>"
    generic, _, _ = parse_generic(html, "https://example.com/lottery", source("geo"), CONFIG)
    center, _, _ = parse_pokemon_center_lottery(
        html,
        "https://www.pokemoncenter-online.com/news?id=999",
        source("pokemon_center_online"),
        CONFIG,
    )
    assert not generic and not center


@freeze_time("2026-09-21")
def test_result_heading_is_not_a_new_lottery() -> None:
    html = f"<title>{FAMILY} 抽選結果</title><main>ポケモンカードゲーム {FAMILY} {PERIOD}</main>"
    cases, _, _ = parse_generic(html, "https://example.com/lottery", source("geo"), CONFIG)
    assert not cases


def test_optional_article_is_not_lost_behind_newer_boxes() -> None:
    from tcg_monitor.parsers.snkrdunk import discover_snkrdunk_article_urls

    html = f'<a href="/articles/100/">ポケカ {FAMILY} 予約・抽選</a>'
    for number in range(101, 106):
        html += f'<a href="/articles/{number}/">ポケカ 新弾{number} 予約・抽選</a>'
    urls = discover_snkrdunk_article_urls(
        html,
        "https://snkrdunk.com",
        source("snkrdunk_pokemon"),
        config=CONFIG,
    )
    assert "https://snkrdunk.com/articles/100/" in urls
    assert len(urls) == 4
