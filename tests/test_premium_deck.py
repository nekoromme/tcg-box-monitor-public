"""プレミアムデッキ例外とシーガルの合同告知を実際の解析経路で検証。"""

from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from tcg_monitor.classifier import classify_product
from tcg_monitor.config import load_config
from tcg_monitor.identity import lottery_dedupe_key
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.source_priority import merge_lotteries

CONFIG = load_config("sites.yaml")
GAME = CONFIG.games["pokemon_card"]
SOURCE = next(s for s in CONFIG.sources if s.id == "yahoo_realtime_seagull_common")
NAME = "30th CELEBRATION プレミアムデッキセット エーフィ・ブラッキー"
KEY = "pokemon_30th_premium_deck"


@pytest.mark.parametrize("name", [
    NAME, "プレミアムデッキセット：エーフィ・ブラッキー",
    "３０ｔｈ ＣＥＬＥＢＲＡＴＩＯＮ プレミアムデッキセット",
    "プレミアムデッキセット エーフィー・ブラッキー",
    "30thセレブレーションプレミアムデッキセット",
])
def test_selected_deck_is_target_without_becoming_a_box(name):
    product = classify_product(GAME, name, name)
    assert product.is_target and not product.is_box
    assert product.product_name == NAME
    assert product.canonical_product_key == KEY


@pytest.mark.parametrize("name", [
    "プレミアムデッキセット 別の商品", "通常デッキセット",
    "スターターデッキ", "エーフィ・ブラッキー デッキケース",
])
def test_other_decks_and_supplies_stay_excluded(name):
    assert not classify_product(GAME, name, name + " 1BOX").is_target


def notice(text):
    # テスト用投稿ID。日時解析が任意の現在日時に依存しないよう固定する。
    posted = datetime(2026, 9, 7, 10, tzinfo=ZoneInfo("Asia/Tokyo"))
    status = (int(posted.timestamp() * 1000) - 1288834974657) << 22
    return (f'<div class="Tweet_TweetContainer__test"><p>{text}</p>'
            '<img src="https://pbs.twimg.com/media/test-premium.jpg">'
            f'<a href="https://x.com/SeagullJP/status/{status}">投稿</a></div>')


@pytest.mark.parametrize("image_only", [False, True])
def test_seagull_body_and_image_detect_box_and_premium_separately(image_only):
    # 公開されたシーガルの9/7告知の表記を再現し、受付期限を添える。
    text = ('9/7（月）より午前10時より ガルモバ会員様限定にて '
            '2回目抽選申込を開始致します。ポケモンカードゲーム MEGA '
            '拡張パック「30th CELEBRATION」② '
            f'・「{NAME}」② 応募期間 9/7 10:00～9/13 20:00')
    html = notice("ポケカ抽選受付開始 詳細は画像をご確認ください" if image_only else text)
    cases, releases, alerts = parse_yahoo_realtime(
        html, SOURCE.discovery_urls[0], SOURCE, CONFIG, date(2026, 9, 7),
        ocr_reader=lambda _: text if image_only else "", known_releases=[],
    )
    assert not alerts and not releases
    assert {c.product_name for c in cases} == {NAME, "拡張パック「30th CELEBRATION」"}
    assert all(c.start_at == datetime(2026, 9, 7, 10, tzinfo=ZoneInfo("Asia/Tokyo"))
               for c in cases)
    assert all(c.end_at == datetime(2026, 9, 13, 20, tzinfo=ZoneInfo("Asia/Tokyo"))
               for c in cases)
    assert len({lottery_dedupe_key(c) for c in cases}) == 2
    assert len(merge_lotteries(cases + cases)[0]) == 2
    assert not parse_yahoo_realtime(
        html, SOURCE.discovery_urls[0], SOURCE, CONFIG, date(2026, 9, 14),
        ocr_reader=lambda _: text if image_only else "", known_releases=[],
    )[0]


def test_opt_out_restores_previous_exclusion():
    game = replace(GAME, additional_products=tuple(
        replace(p, enabled=False) if p.id == KEY else p for p in GAME.additional_products
    ))
    assert not classify_product(game, NAME, NAME).is_target
