"""非BOX例外の取得・日時・配信履歴を実際の解析経路で検証する。"""

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from tcg_monitor.additional_products import additional_matches
from tcg_monitor.classifier import classify_product
from tcg_monitor.cli import (
    _lottery_discord_description,
    _opportunity_title_prefix,
    _opportunity_uses_calendar,
)
from tcg_monitor.config import ConfigError, _additional_products, load_config
from tcg_monitor.models import OpportunityKind, stable_url_identity
from tcg_monitor.non_box_sales import additional_sale_cases
from tcg_monitor.parsers.generic import discover_geo_news_urls, parse_generic, parse_onepiece_topics
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.parsers.official_retailers import (
    discover_official_retailer_urls,
    parse_konami_style,
    parse_premium_bandai_dragonball,
)
from tcg_monitor.parsers.pokemon_center import (
    discover_pokemon_center_news_urls,
    parse_pokemon_center_lottery,
)
from tcg_monitor.parsers.premium_bandai import parse_nyuka_now_premium_bandai
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState

CONFIG = load_config()
DAY25 = "プレミアムカードコレクション -ONE PIECE DAY'25-"
DB = "フュージョンワールド 2nd ANNIVERSARY SET"
FUT = "30th CELEBRATION FUTURISTIC BOX"
JST = ZoneInfo("Asia/Tokyo")


def premium_summary_block(name: str, method: str, item_id: int = 1000000001) -> str:
    return (
        '<h3>プレミアムバンダイ</h3><table>'
        f'<tr><th>対象商品</th><td>ONE PIECEカードゲーム {name}</td></tr>'
        f'<tr><th>販売形式</th><td>{method}</td></tr>'
        '<tr><th>開始日</th><td>10月3日(土)13:00</td></tr>'
        '<tr><th>終了日</th><td>10月30日(金)23:00</td></tr>'
        '<tr><th>特記事項</th><td>2027年4月発送予定</td></tr>'
        f'<tr><th>販売ページ</th><td><a href="https://p-bandai.jp/item/item-{item_id}/">'
        '販売ページ</a></td></tr></table>'
    )


@freeze_time("2026-10-02 03:00:00Z")
@pytest.mark.parametrize("method", ["オンライン先着販売", "受注販売", "予約販売"])
def test_summary_selected_non_lottery_window_keeps_sale_type(method: str) -> None:
    html = '<h2>抽選・予約応募受付中のストア</h2>' + premium_summary_block(DAY25, method)
    cases, _, alerts = parse_nyuka_now_premium_bandai(
        html, "https://nyuka-now.com/archives/97393",
        source("nyuka_now_fullcomp_livepocket"), CONFIG,
    )
    assert not alerts and len(cases) == 1
    assert cases[0].opportunity_kind == OpportunityKind.DIRECT_SALE
    assert cases[0].start_at == datetime(2026, 10, 3, 13, tzinfo=JST)
    assert cases[0].end_at == datetime(2026, 10, 30, 23, tzinfo=JST)
    assert cases[0].official_url == "https://p-bandai.jp/item/item-1000000001/"
    assert stable_url_identity(cases[0].source_url) == "https://nyuka-now.com/archives/97393"
    assert "#:~:text=" in cases[0].source_url
    assert DAY25 in unquote(cases[0].source_url)
    assert unquote(cases[0].source_url).endswith(",10月3日(土)13:00")


@freeze_time("2026-10-02 03:00:00Z")
@pytest.mark.parametrize("name", [
    "LUFFY’s -ドン!!カード-",
    "プレミアムカードコレクション -ONE PIECE DAY'26-",
    "ブースターパック 世界最強の戦士【OP-17】",
])
def test_summary_unselected_sales_are_neither_lotteries_nor_structure_alerts(name: str) -> None:
    cases, _, alerts = parse_nyuka_now_premium_bandai(
        premium_summary_block(name, "オンライン先着販売"),
        "https://nyuka-now.com/archives/97393",
        source("nyuka_now_fullcomp_livepocket"), CONFIG,
    )
    assert not cases and not alerts


@freeze_time("2026-10-02 03:00:00Z")
def test_summary_all_current_blocks_survive_unselected_first_sale_and_ignore_history() -> None:
    html = (
        '<h2>抽選・予約応募受付中のストア</h2>'
        + premium_summary_block("LUFFY’s -ドン!!カード-", "オンライン先着販売")
        + premium_summary_block(DAY25, "受注販売", 1000000002)
        + premium_summary_block("ブースターパック 世界最強の戦士【OP-17】", "WEB抽選受付",
                                1000000003)
        + '<h2>応募受付終了（過去の抽選・予約一覧）</h2>'
        + premium_summary_block(DAY25, "WEB抽選受付", 1000000004)
    )
    cases, _, alerts = parse_nyuka_now_premium_bandai(
        html, "https://nyuka-now.com/archives/97393",
        source("nyuka_now_fullcomp_livepocket"), CONFIG,
    )
    assert not alerts and len(cases) == 2
    assert {case.opportunity_kind for case in cases} == {
        OpportunityKind.DIRECT_SALE, OpportunityKind.LOTTERY,
    }
    assert {case.official_url for case in cases} == {
        "https://p-bandai.jp/item/item-1000000002/",
        "https://p-bandai.jp/item/item-1000000003/",
    }


def test_summary_with_only_ended_premium_bandai_sections_has_no_structure_alert() -> None:
    html = '<h2>応募受付終了</h2>' + premium_summary_block(DAY25, "WEB抽選受付")
    cases, _, alerts = parse_nyuka_now_premium_bandai(
        html, "https://nyuka-now.com/archives/97393",
        source("nyuka_now_fullcomp_livepocket"), CONFIG,
    )
    assert not cases and not alerts


def source(source_id: str):
    return next(item for item in CONFIG.sources if item.id == source_id)


def notice(text: str, account: str = "p_bandai", image: bool = False,
           posted: datetime | None = None) -> str:
    posted = posted or datetime(2026, 10, 2, 10, tzinfo=JST)
    status_id = (int(posted.timestamp() * 1000) - 1288834974657) << 22
    img = '<img src="https://pbs.twimg.com/media/sale.jpg">' if image else ""
    return (f'<div class="Tweet_TweetContainer__test"><p>{text}</p>{img}'
            f'<a href="https://x.com/{account}/status/{status_id}">投稿</a></div>')


@pytest.mark.parametrize("gid,name", [
    ("pokemon_card", FUT),
    ("pokemon_card", "スペシャルBOX「ポケモンセンタートウホク」"),
    ("pokemon_card", "スペシャルBOX ポケモンセンターヒロシマ"),
    ("pokemon_card", "スペシャルBOX ポケモンセンターフクオカ"),
    ("one_piece_card", DAY25),
    ("one_piece_card", "プレミアムカードコレクション 25周年エディション"),
    ("one_piece_card", "ONE PIECEカードゲーム 3rd ANNIVERSARY SET"),
    ("dragon_ball_fusion_world", DB),
    ("yu_gi_oh", "デュエルセット WCS2026"),
    ("gundam_card", "リミテッドＢＯＸ Ｖｅｒ．β"),
])
def test_exact_exceptions_bypass_contents_exclusions(gid: str, name: str) -> None:
    item = classify_product(CONFIG.games[gid], name, name + " スリーブ・カードケース同梱")
    assert item.explicitly_selected and item.is_target and not item.is_box


@pytest.mark.parametrize("gid,name", [
    ("pokemon_card", "ポケモンセンターヒロシマ デッキシールド"),
    ("one_piece_card", "ONE PIECEカードゲーム English 3rd ANNIVERSARY SET"),
    ("dragon_ball_fusion_world", DB + " デジタル版 ジェム"),
    ("dragon_ball_fusion_world", "ONE PIECEカードゲーム 2nd ANNIVERSARY SET"),
    ("lorcana", "ロルカナ ギフトセット スティッチ"),
    ("gundam_card", "ガンダムカードゲーム 1st ANNIVERSARY SET PB03"),
    ("gundam_card", "リミテッドBOX Ver.α"),
])
def test_other_versions_and_unverified_sets_are_not_exceptions(gid: str, name: str) -> None:
    assert not additional_matches(CONFIG.games[gid], name)


@freeze_time("2026-10-02 03:00:00Z")
@pytest.mark.parametrize("name", [
    "ONE PIECEカードゲーム 4th ANNIVERSARY SET",
    "プレミアムカードコレクション -ONE PIECE DAY'26-",
])
def test_unreviewed_families_keep_lottery_candidates_but_do_not_expand_sales(name: str) -> None:
    assert additional_matches(CONFIG.games["one_piece_card"], name)
    assert not additional_sale_cases(name + " 予約受付期間10/3～10/30",
                                     "https://p-bandai.jp/item/item-1/",
                                     source("yahoo_realtime_premium_bandai_onepiece"), CONFIG,
                                     "premium_bandai", "プレミアムバンダイ")


@freeze_time("2026-10-02 03:00:00Z")
@pytest.mark.parametrize("period,kind,start,end", [
    ("予約受付期間：2026年10月3日11時～10月30日23時", "予約",
     datetime(2026, 10, 3, 11, tzinfo=JST), datetime(2026, 10, 30, 23, tzinfo=JST)),
    ("10月3日11:00から予約開始", "予約", datetime(2026, 10, 3, 11, tzinfo=JST), None),
    ("予約開始：10月3日11:00", "予約", datetime(2026, 10, 3, 11, tzinfo=JST), None),
    ("受注受付期間：10/3～10/30 23:00", "受注販売",
     date(2026, 10, 3), datetime(2026, 10, 30, 23, tzinfo=JST)),
    ("受注生産。注文受付期間：10月3日～5日23時", "受注販売",
     date(2026, 10, 3), datetime(2026, 10, 5, 23, tzinfo=JST)),
])
def test_reservation_dates_never_use_release_or_shipping_dates(period, kind, start, end) -> None:
    text = f"{DAY25} 発売日2027年1月20日。{period}。お届け2027年6月1日"
    cases = additional_sale_cases(text, "https://p-bandai.jp/item/item-1000000001/",
                                  source("yahoo_realtime_premium_bandai_onepiece"), CONFIG,
                                  "premium_bandai", "プレミアムバンダイ")
    assert len(cases) == 1
    case = cases[0]
    assert case.start_at == start and case.end_at == end
    assert case.opportunity_kind == OpportunityKind.DIRECT_SALE
    assert kind in _opportunity_title_prefix(case, CONFIG)
    description = _lottery_discord_description(case, CONFIG)
    assert "商品メモ:" in description and "応募締切" not in description
    assert _opportunity_uses_calendar(case)


@freeze_time("2026-10-02 03:00:00Z")
@pytest.mark.parametrize("period", [
    "予約受付中。開始日は未記載。2027年1月20日発売予定",
    "予約開始日時は後日案内。発売日2027年1月20日",
    "2027年1月20日発売。予約受付開始",
    "予約受付期間：10月30日23時まで。2027年1月20日お届け",
    "予約受付開始。受付は10月30日23時まで。2027年1月20日お届け",
])
def test_unknown_start_is_seen_only_and_never_a_guessed_calendar_event(period: str) -> None:
    cases = additional_sale_cases(DAY25 + " " + period, "https://p-bandai.jp/item/item-1/",
                                  source("yahoo_realtime_premium_bandai_onepiece"), CONFIG,
                                  "premium_bandai", "プレミアムバンダイ")
    assert len(cases) == 1
    assert cases[0].opportunity_kind == OpportunityKind.DIRECT_SALE_SEEN
    assert cases[0].start_at == date(2026, 10, 2)
    assert not _opportunity_uses_calendar(cases[0])


@freeze_time("2026-10-02 03:00:00Z")
@pytest.mark.parametrize("period", [
    "予約受付終了", "完売。予約受付期間10/1～10/30",
    "受注受付期間9/1～9/30 23:00", "予約受付期間10/1～10/2 11:00",
    "発売日10/3", "追加生産決定。受付方法は後日お知らせ", "抽選結果を発表",
])
def test_ended_and_production_only_notices_are_not_sale_openings(period: str) -> None:
    assert not additional_sale_cases(DAY25 + " " + period, "https://p-bandai.jp/item/item-1/",
                                     source("yahoo_realtime_premium_bandai_onepiece"), CONFIG,
                                     "premium_bandai", "プレミアムバンダイ")


@freeze_time("2026-10-02 03:00:00Z")
@pytest.mark.parametrize("image_only", [False, True])
@pytest.mark.parametrize("name,gid", [
    (DAY25, "one_piece_card"), (DB, "dragon_ball_fusion_world"),
    ("ガンダムカードゲーム リミテッドBOX Ver.β", "gundam_card"),
])
def test_shared_premium_bandai_feed_handles_body_and_image_sales(image_only, name, gid) -> None:
    text = name + " 受注受付期間10/2 11:00～10/30 23:00"
    src = source("yahoo_realtime_premium_bandai_onepiece")
    html = notice("お知らせ、画像をご確認ください" if image_only else text, image=image_only)
    cases, releases, alerts = parse_yahoo_realtime(
        html, src.discovery_urls[-1], src, CONFIG, date(2026, 10, 2),
        ocr_reader=lambda _: text, known_releases=[],
    )
    assert not alerts and not releases and len(cases) == 1
    assert cases[0].game_id == gid
    assert cases[0].opportunity_kind == OpportunityKind.DIRECT_SALE
    assert cases[0].end_at == datetime(2026, 10, 30, 23, tzinfo=JST)


@freeze_time("2026-10-02 03:00:00Z")
def test_new_sale_path_does_not_expand_to_normal_box_or_deck_preorders() -> None:
    src = source("yahoo_realtime_premium_bandai_onepiece")
    mixed = DAY25 + ' 予約開始10/3。ブースターパック「新たなる皇帝」OP-09 1BOX'
    cases, _, alerts = parse_yahoo_realtime(
        notice(mixed), src.discovery_urls[-1], src, CONFIG, date(2026, 10, 2), known_releases=[],
    )
    assert not alerts and len(cases) == 1 and cases[0].product_name == DAY25
    for text in ('ブースターパック「新たなる皇帝」OP-09 1BOX', 'ONE PIECE スタートデッキ'):
        assert not parse_yahoo_realtime(notice(text + " 予約開始10/3"),
                                       src.discovery_urls[-1], src, CONFIG,
                                       date(2026, 10, 2), known_releases=[])[0]


@freeze_time("2026-10-02 03:00:00Z")
def test_pokemon_center_discovery_and_detail_include_selected_preorder() -> None:
    src = source("pokemon_center_online")
    text = FUT + " 予約受付期間10/3 11:00～10/30 23:00"
    index = f'<a href="/news?id=999">{text}</a>'
    urls = discover_pokemon_center_news_urls(index, "https://www.pokemoncenter-online.com/news/",
                                            src, config=CONFIG)
    assert len(urls) == 1
    cases, _, alerts = parse_pokemon_center_lottery(f"<h1>{text}</h1>", urls[0], src, CONFIG)
    assert not alerts and len(cases) == 1
    assert cases[0].opportunity_kind == OpportunityKind.DIRECT_SALE


@freeze_time("2026-10-02 03:00:00Z")
def test_geo_and_generic_selected_sale_do_not_create_lottery_alerts() -> None:
    src = source("geo")
    text = FUT + " 予約受付期間10/3 11:00～10/30 23:00"
    index = f'<a href="/news/999">{text}</a>'
    assert discover_geo_news_urls(index, "https://geo-online.co.jp/news/", src, CONFIG)
    for url in ("https://geo-online.co.jp/news/999", "https://shop.example/item/999"):
        cases, _, alerts = parse_generic(f"<title>{FUT}</title><h1>{text}</h1>", url, src, CONFIG)
        assert not alerts and len(cases) == 1
        assert cases[0].opportunity_kind == OpportunityKind.DIRECT_SALE


@freeze_time("2026-10-02 03:00:00Z")
def test_official_stores_follow_selected_items_and_parse_made_to_order() -> None:
    for src_id, name, url, parser in (
        ("premium_bandai_dragonball", DB, "https://p-bandai.jp/item/item-1000244759/",
         parse_premium_bandai_dragonball),
        ("konami_style_yugioh", "遊戯王 デュエルセット WCS2026",
         "https://www.konamistyle.jp/products/detail.php?product_id=113602", parse_konami_style),
    ):
        src = source(src_id)
        index_url = src.discovery_urls[0]
        urls = discover_official_retailer_urls(
            f'<a href="{url}">{name}</a>', index_url, src, CONFIG,
        )
        assert urls == [url]
        cases, _, alerts = parser(
            f"<main><h1>{name}</h1><p>受注受付期間10/3～10/30 23:00</p></main>",
            url, src, CONFIG,
        )
        assert not alerts and len(cases) == 1
        assert cases[0].opportunity_kind == OpportunityKind.DIRECT_SALE


@freeze_time("2026-10-02 03:00:00Z")
def test_topics_index_only_notifies_fresh_specific_sales() -> None:
    src = source("premium_bandai_onepiece")
    text = DAY25 + " 予約受付開始"
    html = f'<a href="/topics/999.php">2026.10.02 {text}</a>'
    cases = parse_onepiece_topics(html, src.discovery_urls[0], src, CONFIG)[0]
    assert len(cases) == 1 and cases[0].opportunity_kind == OpportunityKind.DIRECT_SALE_SEEN
    old = html.replace("2026.10.02", "2025.10.02")
    assert not parse_onepiece_topics(old, src.discovery_urls[0], src, CONFIG)[0]


@freeze_time("2026-10-02 03:00:00Z")
def test_seen_sale_upgrade_keeps_delivery_and_later_order_window_is_new(tmp_path: Path) -> None:
    src = source("yahoo_realtime_premium_bandai_onepiece")
    url = "https://p-bandai.jp/item/item-1000000001/"
    seen = additional_sale_cases(DAY25 + " 予約受付中", url, src, CONFIG,
                                 "premium_bandai", "プレミアムバンダイ")[0]
    known = additional_sale_cases(DAY25 + " 予約受付期間10/2～10/30", url, src, CONFIG,
                                  "premium_bandai", "プレミアムバンダイ")[0]
    merged = merge_lotteries([seen, known])[0]
    assert len(merged) == 1 and merged[0].opportunity_kind == OpportunityKind.DIRECT_SALE
    state = MonitorState.load(tmp_path / "state.json")
    state.data["seen_cases"][seen.case_id] = {
        **seen.__dict__, "start_at": seen.start_at.isoformat(),
    }
    state.mark_delivered("lottery:started:" + seen.case_id)
    assert state.migrate_case_identity(known) == seen.case_id
    assert state.delivered("lottery:started:" + known.case_id)
    later = replace(known, start_at=date(2026, 11, 2), end_at=date(2026, 11, 30),
                    case_id="").with_id()
    assert later.case_id != known.case_id
    state.data["seen_cases"][known.case_id] = {
        **known.__dict__, "start_at": known.start_at.isoformat(),
    }
    assert state.migrate_case_identity(later) is None
    assert not state.delivered("lottery:started:" + later.case_id)


@freeze_time("2026-10-02 03:00:00Z")
def test_sale_end_datetime_label_in_future_is_not_a_closed_status() -> None:
    cases = additional_sale_cases(DAY25 + " 予約受付期間10/2～10/30。予約受付終了:10/30 23:00",
                                  "https://p-bandai.jp/item/item-1/",
                                  source("yahoo_realtime_premium_bandai_onepiece"), CONFIG,
                                  "premium_bandai", "プレミアムバンダイ")
    assert len(cases) == 1 and cases[0].end_at == datetime(2026, 10, 30, 23, tzinfo=JST)


@pytest.mark.parametrize("field,value", [("required_keywords", "bad"),
                                         ("exclude_keywords", [""]), ("monitor_sales", "yes"),
                                         ("note", {})])
def test_config_rejects_invalid_exception_guard_fields(field, value) -> None:
    with pytest.raises(ConfigError):
        _additional_products([{"id": "test", "name": "test", "category": "test", field: value}])


@freeze_time("2026-10-02 03:00:00Z")
def test_exception_can_keep_lottery_enabled_while_disabling_sales() -> None:
    game = CONFIG.games["one_piece_card"]
    config = replace(CONFIG, games={**CONFIG.games, "one_piece_card": replace(
        game, additional_products=tuple(replace(item, monitor_sales=False)
                                        for item in game.additional_products),
    )})
    assert additional_matches(config.games["one_piece_card"], DAY25)
    assert not additional_sale_cases(DAY25 + " 予約受付期間10/3～10/30", "https://p-bandai.jp/",
                                     source("yahoo_realtime_premium_bandai_onepiece"), config,
                                     "premium_bandai", "プレミアムバンダイ")


@freeze_time("2026-10-02 03:00:00Z")
@pytest.mark.parametrize("extra", ["リポストして応募", "店頭掲示QRから応募"])
def test_sale_exceptions_keep_disallowed_application_filters(extra: str) -> None:
    src = source("yahoo_realtime_premium_bandai_onepiece")
    text = DAY25 + " 予約受付期間10/2～10/30 " + extra
    assert not parse_yahoo_realtime(notice(text), src.discovery_urls[-1], src, CONFIG,
                                    date(2026, 10, 2), known_releases=[])[0]


@freeze_time("2026-10-02 03:00:00Z")
def test_sale_exception_keeps_required_application_url_scope() -> None:
    src = replace(source("yahoo_realtime_premium_bandai_onepiece"), parser_options={
        **source("yahoo_realtime_premium_bandai_onepiece").parser_options,
        "required_application_url_pattern": r"https://p-bandai\.jp/item/.*",
    })
    text = DAY25 + " 予約受付期間10/2～10/30"
    assert not parse_yahoo_realtime(notice(text), src.discovery_urls[-1], src, CONFIG,
                                    date(2026, 10, 2), known_releases=[])[0]
    html = notice(text).replace("<p>", '<a href="https://t.co/test" '
                               'title="https://p-bandai.jp/item/item-1000237023/">商品</a><p>')
    cases = parse_yahoo_realtime(html, src.discovery_urls[-1], src, CONFIG,
                                date(2026, 10, 2), known_releases=[])[0]
    assert len(cases) == 1
    assert cases[0].official_url == "https://p-bandai.jp/item/item-1000237023/"


@freeze_time("2026-10-02 03:00:00Z")
def test_english_spelling_of_japanese_card_collection_still_gets_sale_rule() -> None:
    cases = additional_sale_cases("PREMIUM CARD COLLECTION -FILM RED- 予約受付期間10/2～10/30",
                                  "https://p-bandai.jp/item/item-1/",
                                  source("yahoo_realtime_premium_bandai_onepiece"), CONFIG,
                                  "premium_bandai", "プレミアムバンダイ")
    assert len(cases) == 1 and cases[0].canonical_product_key == "onepiece_pcc_film_red"


@freeze_time("2026-10-02 03:00:00Z")
def test_non_box_lottery_remains_lottery_and_expired_start_is_not_revived() -> None:
    src = source("yahoo_realtime_konami_style")
    text = "遊戯王 デュエルセット WCS2026 抽選受付期間10/2 10:00～10/3 23:00"
    cases, _, alerts = parse_yahoo_realtime(notice(text, "konamistyle"), src.discovery_urls[-1],
                                          src, CONFIG, date(2026, 10, 2), known_releases=[])
    assert not alerts and len(cases) == 1
    assert cases[0].opportunity_kind == OpportunityKind.LOTTERY
    for ended in (text.replace("10/3 23:00", "10/2 11:00"),
                  text.replace("10/2 10:00～10/3 23:00", "9/18 11:00～9/24 23:59")):
        assert not parse_yahoo_realtime(notice(ended, "konamistyle"), src.discovery_urls[-1],
                                       src, CONFIG, date(2026, 10, 2), known_releases=[])[0]
