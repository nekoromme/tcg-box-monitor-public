from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from tcg_monitor.config import ConfigError, _validated_system, load_config
from tcg_monitor.http_client import FetchResult
from tcg_monitor.identity import release_dedupe_key
from tcg_monitor.models import Release, SourceTier
from tcg_monitor.purchase_review import (
    family_assessment,
    price_message,
    run_purchase_reviews,
)
from tcg_monitor.review_sources import (
    ContentEvidence,
    PriceEvidence,
    ReviewSource,
    card_list_count,
    parse_content,
    parse_snkr_price,
    product_matches,
)
from tcg_monitor.state import MonitorState

JST = ZoneInfo("Asia/Tokyo")


def product() -> Release:
    return Release(
        "yu_gi_oh",
        "遊☆戯☆王 ORIGINAL ARTWORK COLLECTION",
        "スペシャルパック",
        "yac1",
        date(2026, 10, 10),
        None,
        "https://www.yugioh-card.com/japan/products/yac1/",
        "https://www.yugioh-card.com/japan/products/",
        SourceTier.OFFICIAL,
        "official",
        "high",
    ).with_id()


def snkr_html(
    *,
    price: int | None = 13001,
    name: str = "",
    day: str = "2026年10月10日",
    display_regular: str = "¥10,000",
) -> str:
    # Minimal observed Next flight schema; a recommendation deliberately has a lower price.
    obj = {
        "apparelData": {
            "id": 886014,
            "regularPrice": 10000,
            "displayRegularPrice": display_regular,
            "minPrice": 1,
            "name": name or 'Yu-Gi-Oh "ORIGINAL ARTWORK COLLECTION" JP Edition Box',
            "localizedName": name
            or "遊戯王OCG オリジナル アートワーク コレクション 日本版 ボックス",
            "displayReleasedAt": day,
        },
        "apparelId": 886014,
        "listings": [
            {"variant": {"sizeName": "1個"}, "minNewListingPrice": price},
            {"variant": {"sizeName": "2個"}, "minNewListingPrice": 20000},
        ],
        "recommendation": {
            "apparelId": 123,
            "listings": [{"variant": {"sizeName": "1個"}, "minNewListingPrice": 5}],
        },
    }
    payload = json.dumps([1, "52:" + json.dumps(obj)])
    return f"<html lang='ja'><script>self.__next_f.push({payload})</script></html>"


@pytest.mark.parametrize("price,expected", [(12999, False), (13000, False), (13001, True)])
def test_strict_thirty_percent_threshold(price: int, expected: bool) -> None:
    decision, message = price_message(
        product(),
        PriceEvidence("found", price=price, msrp=10000),
        ContentEvidence(),
        datetime(2026, 10, 8, 0, 4, tzinfo=JST),
    )
    assert ("基準達成" in decision) is expected
    assert "最安出品" in message
    assert "JST" in message


def test_live_flight_schema_uses_this_product_quantity_one_only() -> None:
    result = parse_snkr_price(snkr_html(), "https://snkrdunk.com/apparels/886014", product())
    assert result.status == "found"
    assert result.price == 13001
    assert result.msrp == 10000


def test_no_quantity_one_price_does_not_use_catalog_or_multiple_boxes() -> None:
    result = parse_snkr_price(
        snkr_html(price=None), "https://snkrdunk.com/apparels/886014", product()
    )
    assert result.status == "unpriced"
    assert result.price is None


def test_non_yen_price_is_not_used_even_for_japanese_edition() -> None:
    result = parse_snkr_price(
        snkr_html(display_regular="$100"), "https://snkrdunk.com/apparels/886014", product()
    )
    assert result.status == "error"
    assert "日本円" in result.error


@pytest.mark.parametrize(
    "name",
    [
        'Yu-Gi-Oh "OTHER ARTWORK COLLECTION" JP Edition Box',
        'Yu-Gi-Oh "ORIGINAL ARTWORK COLLECTION" English Edition Box',
        'Yu-Gi-Oh "ORIGINAL ARTWORK COLLECTION" Asia Edition Box',
        'Yu-Gi-Oh "ORIGINAL ARTWORK COLLECTION" JP Edition Single Card',
        'Pokemon "ORIGINAL ARTWORK COLLECTION" JP Edition Box',
    ],
)
def test_wrong_product_language_game_or_unit_is_rejected(name: str) -> None:
    result = parse_snkr_price(
        snkr_html(name=name), "https://snkrdunk.com/apparels/886014", product()
    )
    assert result.status == "mismatch"


def test_wrong_release_date_and_markup_are_indeterminate() -> None:
    assert (
        parse_snkr_price(
            snkr_html(day="2025年10月10日"), "https://snkrdunk.com/apparels/886014", product()
        ).status
        == "mismatch"
    )
    assert (
        parse_snkr_price("Access denied", "https://snkrdunk.com/apparels/886014", product()).status
        == "error"
    )
    decision, message = price_message(
        product(),
        PriceEvidence("found", price=13001, msrp=10000),
        ContentEvidence(msrp=9000),
        datetime(2026, 10, 8, tzinfo=JST),
    )
    assert decision == "判定不能"
    assert "定価不一致" in message


def test_early_content_checklist_is_scoped_and_does_not_invent_absence() -> None:
    result = parse_content(
        """
        <main><section id='introduction'>初回生産分BOXには特典パックを同梱。
        シリアルNo.001～100付き グランドマスターレアも存在。</section>
        <section id='information'>1パック 385円（本体価格350円）
        1ボックス：15パック入り カード種類：全80種
        ウルトラレア18種にはグランドマスターレア仕様が存在。</section>
        <a href='https://www.db.yugioh-card.com/yugiohdb/card_search.action?pid=123'>収録カード</a>
        <aside>関連商品 オーバーフレーム</aside></main>
    """,
        "https://www.yugioh-card.com/japan/products/test/",
    )
    assert result.msrp == 5775
    assert result.total_cards == 80
    assert result.features["初回生産限定・初回BOX特典"].startswith("あり")
    assert result.features["グランドマスターレア"].startswith("あり")
    assert result.features["特殊イラスト・特殊仕様"].startswith("不明")
    assert "pid=123" in result.card_list_url
    assert any("001~100" in item for item in result.rarity_details)
    assert not result.complete
    assert parse_content("1パック 385円", "url").msrp is None


def test_card_count_ignores_repeated_links_and_global_search_is_not_a_set_list() -> None:
    assert (
        card_list_count("""<main><a href='?cid=1'>a</a><a href='?cid=1&language=ja'>b</a>
        <a href='?cid=2'>c</a></main><aside><a href='?cid=3'>d</a></aside>""")
        == 2
    )
    result = parse_content(
        "<a href='/card-search/?language=ja'>カード検索</a>", "https://example.com/product"
    )
    assert result.card_list_url == "https://example.com/product"


@pytest.fixture
def monitor(tmp_path: Path):  # type: ignore[no-untyped-def]
    config = load_config("sites.yaml")
    state = MonitorState.load(tmp_path / "state.json")
    discord = Mock()
    discord.send.return_value = {"status": "sent"}
    source = Mock(spec=ReviewSource)
    source.content.return_value = ContentEvidence(url=product().official_url, msrp=10000)
    source.price.return_value = PriceEvidence(
        "found", price=13001, msrp=10000, url="https://snkrdunk.com/apparels/886014"
    )
    return config, state, discord, source


def run(monitor, day: int, hour: int = 0, releases=None):  # type: ignore[no-untyped-def]
    config, state, discord, source = monitor
    return run_purchase_reviews(
        config,
        state,
        [product()] if releases is None else releases,
        discord,
        datetime(2026, 10, day, hour, 4, tzinfo=JST),
        source=source,
    )


def test_exactly_two_phases_survive_state_reload_and_missing_current_discovery(monitor) -> None:  # type: ignore[no-untyped-def]
    config, state, discord, source = monitor
    state.data["seen_releases"][product().release_id] = asdict(product())
    run(monitor, 2)  # 8 days out, content checked but no message.
    assert discord.send.call_count == 0
    run(monitor, 3)
    run(monitor, 3, 2)
    assert discord.send.call_count == 1
    assert "早期" in discord.send.call_args.args[0]
    run(monitor, 7)
    source.price.assert_not_called()
    reloaded = MonitorState.load(state.path)
    later = config, reloaded, discord, source
    run(later, 8, releases=[])
    assert discord.send.call_count == 2
    assert "基準達成" in discord.send.call_args.args[0]
    run(later, 8, 2, releases=[])
    run(later, 9, releases=[])
    run(later, 10, releases=[])
    assert discord.send.call_count == 2
    assert source.price.call_count == 1


def test_d2_missing_page_waits_for_d1_and_errors_are_not_classed_as_missing(monitor) -> None:  # type: ignore[no-untyped-def]
    _, state, discord, source = monitor
    run(monitor, 3)
    source.price.return_value = PriceEvidence("missing", error="商品未掲載")
    run(monitor, 8)
    run(monitor, 8, 2)
    assert source.price.call_count == 1
    assert discord.send.call_count == 1
    source.price.return_value = PriceEvidence("found", price=13000, msrp=10000)
    run(monitor, 9)
    assert discord.send.call_count == 2
    assert "未達" in discord.send.call_args.args[0]
    assert state.data["purchase_reviews"][release_dedupe_key(product())]["price_sent"]


def test_final_unknown_notice_is_second_phase_and_never_a_negative_decision(monitor) -> None:  # type: ignore[no-untyped-def]
    _, state, discord, source = monitor
    run(monitor, 3)
    source.price.return_value = PriceEvidence("error", error="HTTP 403")
    run(monitor, 8)
    run(monitor, 8, 2)
    assert source.price.call_count == 2
    run(monitor, 9, 18)
    assert discord.send.call_count == 1
    run(monitor, 9, 20)
    run(monitor, 9, 22)
    assert discord.send.call_count == 2
    assert "判定不能" in discord.send.call_args.args[0]
    assert state.data["purchase_reviews"][release_dedupe_key(product())]["decision"] == "判定不能"


def test_complete_list_can_bring_early_phase_forward(monitor) -> None:  # type: ignore[no-untyped-def]
    _, _, discord, source = monitor
    source.content.return_value = ContentEvidence(complete=True, card_count=80, total_cards=80)
    run(monitor, 1)
    assert discord.send.call_count == 1
    assert "80/80" in discord.send.call_args.args[1]


def test_dry_run_or_delivery_failure_never_consumes_a_phase(monitor) -> None:  # type: ignore[no-untyped-def]
    _, state, discord, _ = monitor
    discord.send.return_value = {"status": "dry_run"}
    run(monitor, 3)
    record = state.data["purchase_reviews"][release_dedupe_key(product())]
    assert not record.get("early_sent")
    discord.send.side_effect = RuntimeError("webhook failed")
    run(monitor, 3, 2)
    assert not record.get("early_sent")
    discord.send.side_effect = None
    discord.send.return_value = {"status": "sent"}
    run(monitor, 3, 4)
    assert record.get("early_sent")


def test_postponed_release_updates_schedule_without_third_notification(monitor) -> None:  # type: ignore[no-untyped-def]
    _, _, discord, source = monitor
    run(monitor, 3)
    postponed = replace(product(), release_date=date(2026, 10, 20))
    run(monitor, 8, releases=[postponed])
    source.price.assert_not_called()
    run(monitor, 18, releases=[postponed])
    assert discord.send.call_count == 2
    run(monitor, 19, releases=[postponed])
    assert discord.send.call_count == 2


def test_japan_midnight_is_price_day_even_when_utc_is_previous_day(monitor) -> None:  # type: ignore[no-untyped-def]
    config, state, discord, source = monitor
    run(monitor, 3)
    run_purchase_reviews(
        config,
        state,
        [product()],
        discord,
        datetime(2026, 10, 7, 14, 59, tzinfo=UTC),
        source=source,
    )
    source.price.assert_not_called()
    run_purchase_reviews(
        config, state, [product()], discord, datetime(2026, 10, 7, 15, 4, tzinfo=UTC), source=source
    )
    assert discord.send.call_count == 2


def test_disabled_games_unconfirmed_releases_and_release_day_do_not_notify(monitor) -> None:  # type: ignore[no-untyped-def]
    config, state, discord, source = monitor
    disabled = replace(config, enabled_game_ids=frozenset({"pokemon_card"}))
    run((disabled, state, discord, source), 8)
    run(monitor, 8, releases=[replace(product(), source_tier=SourceTier.SECONDARY)])
    run(monitor, 10)
    assert discord.send.call_count == 0
    source.content.assert_not_called()


def test_search_missing_and_provider_blocked_are_distinct() -> None:
    fetcher = Mock()
    fetcher.fetch.return_value = FetchResult("search", 403, "Forbidden", {})
    source = ReviewSource(fetcher)
    assert source.price(product()).status == "error"
    fetcher.fetch.return_value = FetchResult(
        "search", 200, "<title>testのおすすめアイテム</title>", {}
    )
    assert source.price(product()).status == "missing"


def test_generic_or_unofficial_pages_cannot_supply_another_sets_features() -> None:
    fetcher = Mock()
    fetcher.fetch.return_value = FetchResult(
        "index", 200, "<title>商品情報</title><main>別の商品にはグランドマスターレア</main>", {}
    )
    result = ReviewSource(fetcher).content(product())
    assert result.error
    assert result.features == {}
    result = ReviewSource(fetcher).content(
        replace(product(), official_url="https://shop.example/releases/")
    )
    assert result.error
    assert result.card_index_url


def test_japanese_marketplace_translation_is_discovered_then_quantity_price_is_read() -> None:
    fetcher = Mock()
    search = """<title>ORIGINAL ARTWORK COLLECTIONのおすすめアイテム</title>
    <a href='/apparels/886014'>遊戯王OCG スペシャルパック
    「遊☆戯☆王 オリジナル アートワーク コレクション」日本版 ボックス</a>"""
    fetcher.fetch.side_effect = [
        FetchResult("search", 200, search, {}),
        FetchResult("product", 200, snkr_html(), {}),
    ]
    result = ReviewSource(fetcher).price(product())
    assert result.status == "found"
    assert result.price == 13001
    assert result.url == "https://snkrdunk.com/apparels/886014"


def test_shared_set_name_does_not_match_another_box_or_deck_variant() -> None:
    regular = replace(
        product(), game_id="pokemon_card", product_name="拡張パック「30th CELEBRATION」"
    )
    assert product_matches(
        regular, ["ポケモンカードゲームMEGA 拡張パック「30th CELEBRATION」ボックス"]
    )
    assert not product_matches(
        regular,
        [
            "ポケモンカードゲームMEGA 構築デッキ「30th CELEBRATION "
            "プレミアムデッキセット エーフィ・ブラッキー」"
        ],
    )


def test_limited_family_is_conditional_and_not_claimed_to_be_limited_production() -> None:
    family, rank, reason = family_assessment(
        replace(product(), product_name="LIMITED PACK WCS 2026")
    )
    assert family == "LIMITED系"
    assert rank == "条件付き"
    assert "名称だけ" in reason


@pytest.mark.parametrize(
    "settings", [None, {"enabled": "true"}, {"early_lead_days": {"yu_gi_oh": 2}}]
)
def test_review_config_rejects_invalid_settings(settings) -> None:  # type: ignore[no-untyped-def]
    system = dict(load_config("sites.yaml").system)
    system["purchase_review"] = settings
    with pytest.raises(ConfigError):
        _validated_system(system)
