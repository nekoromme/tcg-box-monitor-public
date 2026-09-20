from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tcg_monitor.config import load_config
from tcg_monitor.parsers.furuichi import parse_furuichi_lottery_detail
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime

URL = "https://www.furu1.net/news/news_information/uyl20260916"
DEADLINE = "\nについて\n受付期間 : 2026年9月20日(日)23:00まで"


def parse(heading, text, cache=None, meta=None, reader=None):
    config = load_config("sites.yaml")
    source = next(s for s in config.sources if s.id == "furuichi_official_lottery")
    html = (
        '<meta property="article:published_time" content="2026-09-16">'
        f"<h1>{heading}抽選受付について</h1>"
        '<img src="/storage/news/news_information/uyl20260916/notice.jpg">'
    )
    return parse_furuichi_lottery_detail(
        html,
        URL,
        source,
        config,
        detected_on=date(2026, 9, 20),
        ocr_reader=reader or (lambda urls: text),
        ocr_cache=cache,
        ocr_cache_meta=meta,
    )


def test_actual_mixed_union_arena_yugioh_saved_ocr_recovers():
    text = Path("tests/fixtures/furuichi_uyl20260916_ocr.txt").read_text()
    cache = {URL: text}
    cases, _, alerts = parse(
        "UNION ARENA(魔法少女まどか☆マギカ)、遊☆戯☆王オフィシャルカードゲーム",
        text,
        cache,
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].game_id == "yu_gi_oh"
    assert "ORIGINAL ARTWORK COLLECTION" in cases[0].product_name
    assert cases[0].start_at == date(2026, 9, 16)
    assert cases[0].end_at == datetime(2026, 9, 20, 23, tzinfo=ZoneInfo("Asia/Tokyo"))


@pytest.mark.parametrize(
    "game,heading,product",
    [
        ("pokemon_card", "ポケモンカードゲーム", "ポ ケ モ ン カ ー ドゲーム 拡張パック テスト"),
        (
            "one_piece_card",
            "ONE PIECEカードゲーム",
            "O N E P I E C Eカードゲーム ブースターパック テスト [OP-17]",
        ),
        (
            "dragon_ball_fusion_world",
            "フュージョンワールド",
            "フ ュ ー ジ ョ ンワールド ブースターパック テスト [FB11]",
        ),
        ("yu_gi_oh", "遊☆戯☆王", "和遊戯※王 ORIGINAL ARTWORK COLLECTION"),
        ("lorcana", "ロルカナ", "ロ ル カ ナ ブースターパック テスト"),
        (
            "gundam_card",
            "ガンダムカードゲーム",
            "ガ ン ダ ムカードゲーム ブースターパック テスト [GD05]",
        ),
    ],
)
def test_all_six_games_survive_ocr_spacing(game, heading, product):
    cases, _, alerts = parse(heading, product + DEADLINE)
    assert not alerts
    assert [case.game_id for case in cases] == [game]


@pytest.mark.parametrize(
    "game,heading,product",
    [
        ("one_piece_card", "ONE PIECEカードゲーム", "読取不能 ブースターパック テスト [OP-17]"),
        (
            "dragon_ball_fusion_world",
            "フュージョンワールド",
            "読取不能 ブースターパック テスト [FB11]",
        ),
        ("yu_gi_oh", "遊戯王", "読取不能 ORIGINAL ARTWORK COLLECTION"),
        ("gundam_card", "ガンダムカードゲーム", "読取不能 ブースターパック テスト [GD05]"),
    ],
)
def test_unique_product_evidence_recovers_broken_game_name(game, heading, product):
    cases, _, alerts = parse(heading, product + DEADLINE)
    assert not alerts
    assert [case.game_id for case in cases] == [game]


def test_generic_booster_not_attributed_to_heading_game_and_failed_cache_retried():
    text = "UNION ARENA ブースターパック 魔法少女まどか☆マギカ" + DEADLINE
    cache, meta = {URL: text}, {URL: {"updated_at": "2026-09-16"}}
    cases, _, alerts = parse("UNION ARENA、遊戯王", text, cache, meta)
    assert not cases
    assert alerts[0].reason_code == "furuichi_box_products_missing"
    assert URL not in cache and URL not in meta
    calls = []

    def reread(urls):
        calls.append(urls)
        return "遊戯王 ORIGINAL ARTWORK COLLECTION" + DEADLINE

    cases, _, alerts = parse("UNION ARENA、遊戯王", "", cache, meta, reread)
    assert len(cases) == len(calls) == 1
    assert not alerts


def test_partial_mixed_failure_keeps_good_case_and_invalidates_cache():
    text = "ONE PIECEカードゲーム ブースターパック テスト [OP-17]" + DEADLINE
    cache = {URL: text}
    cases, _, alerts = parse("ONE PIECEカードゲーム、ロルカナ", text, cache)
    assert [case.game_id for case in cases] == ["one_piece_card"]
    assert [alert.game_id for alert in alerts] == ["lorcana"]
    assert URL not in cache


def test_missing_dates_invalidates_nonempty_cache():
    text = "遊戯王 ORIGINAL ARTWORK COLLECTION"
    cache = {URL: text}
    cases, _, alerts = parse("遊戯王", text, cache)
    assert not cases and alerts
    assert URL not in cache


def test_changed_image_url_rereads_successful_cache():
    text = "遊戯王 ORIGINAL ARTWORK COLLECTION" + DEADLINE
    cache = {URL: "破損"}
    meta = {URL: {"image_urls": ["https://www.furu1.net/old.jpg"]}}
    cases, _, alerts = parse("遊戯王", text, cache, meta)
    assert len(cases) == 1 and not alerts
    assert cache[URL] == text


@pytest.mark.parametrize(
    "heading,product",
    [
        ("遊戯王", "読取不能 ORIGINAL ARTWORK COLLECTION プレイマット"),
        ("ONE PIECEカードゲーム", "読取不能 スタートデッキ [OP-17]"),
        ("ガンダムカードゲーム", "読取不能 スリーブ [GD05]"),
    ],
)
def test_recovery_does_not_bypass_product_exclusions(heading, product):
    cases, _, _ = parse(heading, product + DEADLINE)
    assert not cases


def test_social_product_parse_failure_invalidates_saved_ocr():
    config = load_config("sites.yaml")
    source = next(s for s in config.sources if s.id == "yahoo_realtime_batoloco_morioka")
    url = "https://x.com/batoloco_mrok/status/2101495716330045594"
    html = (
        f'<article><p>遊戯王 抽選受付開始 詳細は画像で</p><a href="{url}">投稿</a>'
        '<img src="https://pbs.twimg.com/media/test.jpg"></article>'
    )
    cache, meta = {url: "と\ngana"}, {url: {"updated_at": "2026-09-20"}}
    cases, _, alerts = parse_yahoo_realtime(
        html,
        source.discovery_urls[0],
        source,
        config,
        detected_on=date(2026, 9, 20),
        ocr_cache=cache,
        ocr_cache_meta=meta,
    )
    assert not cases
    assert any(a.reason_code == "yahoo_lottery_post_without_product" for a in alerts)
    assert url not in cache and url not in meta
