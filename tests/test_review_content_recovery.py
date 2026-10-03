from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from tcg_monitor.config import load_config
from tcg_monitor.http_client import FetchResult
from tcg_monitor.identity import release_dedupe_key
from tcg_monitor.models import Release, SourceTier
from tcg_monitor.purchase_review import early_message, run_purchase_reviews
from tcg_monitor.review_content import CONTENT_VERSION, usable_content
from tcg_monitor.review_modes import PurchaseReviewModes
from tcg_monitor.review_sources import (
    ContentEvidence,
    ReviewSource,
    card_list_count,
    parse_content,
)
from tcg_monitor.state import MonitorState

FIXTURES = Path(__file__).parent / "fixtures"
JST = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 10, 2, 18, 40, tzinfo=JST)
LORCANA = "https://www.takaratomy.co.jp/products/disneylorcana/product/hyperia-city/booster-pack/"


def product() -> Release:
    return Release(
        "lorcana",
        "ブースターパック「ハイペリアシティ」",
        "ブースターパック",
        "ハイペリアシティ",
        date(2026, 10, 16),
        None,
        LORCANA,
        LORCANA,
        SourceTier.OFFICIAL,
        "official",
        "high",
    ).with_id()


def observed(name: str) -> str:
    return (FIXTURES / f"review_{name}.html").read_text()


def test_observed_lorcana_has_published_content_not_unknown_checkboxes() -> None:
    content = parse_content(observed("lorcana-booster"), LORCANA)
    assert content.msrp == 5280
    assert content.preview_images == 35
    assert content.card_count is None and not content.complete
    assert content.features["作品固有の特殊レア"].startswith("あり")
    assert content.features["BOX同梱・購入特典（初回限定とは別）"].startswith("あり")
    assert content.features["初回生産限定・初回BOX特典"].startswith("不明")
    text = early_message(product(), content, NOW, 14)
    assert all(name in text for name in ("ミッキーマウス", "シンデレラ", "ミニーマウス"))
    assert text.count("\n・") == 2  # 特殊レアと特典だけ。広告文や全チェック項目は並べない。
    assert "35種" not in text and "全公開は未確認" in text
    assert "種別の目安" in text and "5,280円" in text
    assert "不明（公式記載" not in text and text.count("https://") == 1
    assert len(text) < 500 and len(text.splitlines()) <= 6


def test_official_lorcana_search_without_this_set_is_separate_from_product_preview() -> None:
    fetcher = Mock()
    fetcher.fetch.side_effect = [
        FetchResult(LORCANA, 200, observed("lorcana-booster"), {}),
        FetchResult(
            "env", 200, "export const formDefault = {sets: {sets: ['ヴァインズ・アタック！']}};", {}
        ),
    ]
    result = ReviewSource(fetcher).content(product())
    assert usable_content(result)
    assert "選択肢なし" in result.list_status
    assert result.msrp == 5280
    assert result.card_count is None


def test_list_transport_failure_keeps_published_lorcana_content() -> None:
    fetcher = Mock()
    fetcher.fetch.side_effect = [
        FetchResult(LORCANA, 200, observed("lorcana-booster"), {}),
        RuntimeError("blocked"),
    ]
    result = ReviewSource(fetcher).content(product())
    assert result.error == "" and result.msrp == 5280
    assert "取得失敗" in result.list_status


def test_bandai_specs_and_konami_bonus_pack_are_not_lost_or_confused() -> None:
    assert parse_content(observed("dragonball-fb12"), "url").total_cards == 123
    gundam = parse_content(observed("gundam-gd06"), "url")
    assert gundam.total_cards == 135
    assert "ガンダムZZ" in " ".join(gundam.highlights)
    onepiece = parse_content(observed("onepiece-eb05"), "url")
    assert onepiece.total_cards == 75
    # The 240 yen pack price cannot become a made-up BOX price.
    assert onepiece.msrp is None
    yugioh = parse_content(observed("yugioh-imph"), "url")
    assert yugioh.total_cards == 80  # Separate +1 bonus pack is 15 kinds.
    assert yugioh.msrp == 5940


def test_pokemon_special_rarity_image_links_and_related_goods_scope() -> None:
    # Observed markup patterns from the official 30th CELEBRATION product page.
    content = parse_content(
        "<main><p>FUR（フューチャリスティックレア）のミュウexが登場！"
        "このカードはアーティストの描き下ろし！</p>"
        "<img src='/images/m6a/cards/m6a_135.png' alt='ミュウex'>"
        "<a href='https://www.pokemon-card.com/card-search/?se_ta=100'>"
        "<img alt='カードリスト'></a>"
        "<section class='Others_others__062i2'>別の商品：初回生産限定特典</section></main>",
        "https://www.30th.pokemon-card.com/product/m6a",
    )
    assert content.features["作品固有の特殊レア"].startswith("あり")
    assert content.features["初回生産限定・初回BOX特典"].startswith("不明")
    assert content.preview_images == 1
    assert "se_ta=100" in content.card_list_url


def test_h2_product_title_and_official_catalog_resolution() -> None:
    release = replace(
        product(),
        game_id="one_piece_card",
        product_name=(
            "ONE PIECEカードゲーム エクストラブースター ONE PIECE Heroines Edition vol.2【EB-05】"
        ),
        official_url="",
        source_url="https://www.c-labo.jp/special/2028/",
    )
    fetcher = Mock()
    fetcher.fetch.side_effect = [
        FetchResult(
            "catalog",
            200,
            "<main><a href='/products/eb05.html'>"
            "エクストラブースター ONE PIECE Heroines Edition vol.2【EB-05】</a></main>",
            {},
        ),
        FetchResult("product", 200, observed("onepiece-eb05"), {}),
        FetchResult(
            "cards", 200, "<main><select><option value='550204'>EB-04</option></select></main>", {}
        ),
    ]
    result = ReviewSource(fetcher).content(release)
    assert result.url == "https://www.onepiece-cardgame.com/products/eb05.html"
    assert result.total_cards == 75 and usable_content(result)
    assert "選択肢なし" in result.list_status


def test_pokemon_dynamic_catalog_resolves_official_subdomain_and_rejects_unrelated_url() -> None:
    release = replace(
        product(),
        game_id="pokemon_card",
        product_name="拡張パック「30th CELEBRATION」",
        official_url="https://www.pokemon-card.com/products/index.html?productType=expansion",
    )
    payload = {
        "result": 1,
        "errMsg": "",
        "hitCnt": 1,
        "thisPage": 1,
        "maxPage": 1,
        "products": [
            {
                "productTitle": "拡張パック「30th CELEBRATION」",
                "link_detailPage": "https://www.30th.pokemon-card.com/product/m6a",
            }
        ],
    }
    fetcher = Mock()
    fetcher.fetch.return_value = FetchResult("api", 200, json.dumps(payload), {})
    source = ReviewSource(fetcher)
    assert (
        source._product_url(release, release.official_url)
        == payload["products"][0]["link_detailPage"]
    )
    payload["products"][0]["link_detailPage"] = "https://shop.example.com/card"
    fetcher.fetch.return_value = FetchResult("api", 200, json.dumps(payload), {})
    assert source._product_url(release, release.official_url) == ""


def test_unknown_only_is_pending_then_recovery_sends_once(tmp_path: Path) -> None:
    config = load_config("sites.yaml")
    state = MonitorState.load(tmp_path / "state.json")
    source = Mock(spec=ReviewSource)
    source.content.return_value = ContentEvidence(version=CONTENT_VERSION)
    discord = Mock()
    discord.send.return_value = {"status": "sent"}
    modes = PurchaseReviewModes(True, False)
    for hour in (18, 20, 22):
        run_purchase_reviews(
            config, state, [product()], discord, NOW.replace(hour=hour), source=source, modes=modes
        )
    assert discord.send.call_count == 0
    assert not state.data["purchase_reviews"][release_dedupe_key(product())].get("early_sent")
    assert source.content.call_count == 3
    source.content.return_value = parse_content(observed("lorcana-booster"), LORCANA)
    run_purchase_reviews(config, state, [product()], discord, NOW, source=source, modes=modes)
    state.save()
    run_purchase_reviews(
        config, MonitorState.load(state.path), [product()], discord, NOW, source=source, modes=modes
    )
    assert discord.send.call_count == 1


def test_legacy_empty_notification_is_repaired_once_without_resetting_history(
    tmp_path: Path,
) -> None:
    config = load_config("sites.yaml")
    state = MonitorState.load(tmp_path / "state.json")
    key = release_dedupe_key(product())
    original_sent = "2026-10-02T02:37:11+09:00"
    state.data["purchase_reviews"][key] = {
        "early_sent": original_sent,
        "content_checked_on": "2026-10-02",
        "content": asdict(ContentEvidence(url=LORCANA, features={"特殊レア": "不明"})),
    }
    source = Mock(spec=ReviewSource)
    source.content.return_value = parse_content(observed("lorcana-booster"), LORCANA)
    discord = Mock()
    discord.send.return_value = {"status": "sent"}
    modes = PurchaseReviewModes(True, False)
    for _ in range(2):
        run_purchase_reviews(config, state, [product()], discord, NOW, source=source, modes=modes)
        state = MonitorState.load(state.path)
    assert discord.send.call_count == 1
    assert "補足" in discord.send.call_args.args[0]
    assert state.data["purchase_reviews"][key]["early_sent"] == original_sent
    assert state.data["purchase_reviews"][key]["early_repair_sent"]


def test_parallel_images_and_repeated_links_do_not_inflate_card_kinds() -> None:
    assert (
        card_list_count(
            "<main><img data-src='/card/jp/FB11-001_f.webp'>"
            "<img data-src='/card/jp/FB11-001_f_p1.webp'>"
            "<img data-src='/card/jp/FB11-002.webp'></main>"
        )
        == 2
    )


def test_repair_delivery_failure_retries_after_content_cache_becomes_usable(tmp_path: Path) -> None:
    config = load_config("sites.yaml")
    state = MonitorState.load(tmp_path / "state.json")
    key = release_dedupe_key(product())
    state.data["purchase_reviews"][key] = {"early_sent": "2026-10-02T02:37:11+09:00"}
    source = Mock(spec=ReviewSource)
    source.content.return_value = parse_content(observed("lorcana-booster"), LORCANA)
    discord = Mock()
    discord.send.side_effect = RuntimeError("delivery failed")
    modes = PurchaseReviewModes(True, False)
    run_purchase_reviews(config, state, [product()], discord, NOW, source=source, modes=modes)
    assert state.data["purchase_reviews"][key]["early_repair_required"]
    state.save()
    state = MonitorState.load(state.path)
    discord.send.side_effect = None
    discord.send.return_value = {"status": "sent"}
    run_purchase_reviews(config, state, [product()], discord, NOW, source=source, modes=modes)
    assert discord.send.call_count == 2
    assert state.data["purchase_reviews"][key]["early_repair_sent"]


def test_ignored_set_query_is_not_counted_as_complete() -> None:
    release = replace(product(), game_id="one_piece_card", product_name="EB-05")
    result = ContentEvidence(
        url="https://www.onepiece-cardgame.com/products/eb05.html",
        card_list_url="https://www.onepiece-cardgame.com/products/eb05.html",
        card_index_url="https://www.onepiece-cardgame.com/cardlist/",
        total_cards=1,
    )
    fetcher = Mock()
    fetcher.fetch.side_effect = [
        FetchResult("index", 200, "<option value='550205'>EB-05</option>", {}),
        FetchResult(
            "wrong-default",
            200,
            "<option selected value='550204'>EB-04</option>"
            "<img data-src='/images/cardlist/card/EB04-001.png'>",
            {},
        ),
    ]
    ReviewSource(fetcher)._card_list(release, result, "")
    assert result.card_count is None and not result.complete
    assert "照合できず" in result.list_status
