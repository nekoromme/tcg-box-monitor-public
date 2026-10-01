from __future__ import annotations

import pytest
from freezegun import freeze_time

from tcg_monitor.config import load_config
from tcg_monitor.parsers.retailer_lottery import parse_retailer_lottery_detail

CONFIG = load_config("sites.yaml")
SOURCE = next(s for s in CONFIG.sources if s.id == "tokyo_otaku_mode_lottery")
URL = "https://ja.otakumode.com/blogs/news/lottery"
BOX = "ポケモンカードゲーム MEGA 拡張パック ストームエメラルダ BOX"
DECK = "ポケモンカードゲーム MEGA スタートデッキ100 バトルコレクション"


def article(product=BOX, heading="【抽選販売】抽選応募受付開始についてのお知らせ",
            deadline="〜2026年10月3日 12時00分", related=""):
    # Related articles are nested inside Shopify's content container.
    return f"""<h2>カートにアイテムが追加されました</h2>
    <article class="article-template"><h1>{heading}</h1>
    <time datetime="2026-10-01T00:00:00Z">2026年10月1日</time>
    <div class="article-template__content">
    <p>下記の商品につきまして、抽選応募を開始いたします。</p>
    <p>{product}</p><h2>【抽選応募 受付期間】</h2><p>{deadline}</p>
    <h2>【当選発表】</h2><p>2026年10月5日以降予定</p>
    <a href="https://docs.google.com/forms/d/e/current/viewform">ご応募はこちら</a>
    <section class="related-articles-section">{related}</section>
    </div></article><script>{BOX} 抽選受付期間</script>"""


@freeze_time("2026-10-01 10:00:00+09:00")
@pytest.mark.parametrize("product", [BOX, DECK])
def test_closed_article_is_not_an_unreadable_box(product):
    diagnostics = {}
    cases, releases, alerts = parse_retailer_lottery_detail(
        article(product, heading="受付終了【抽選販売】 抽選応募受付開始についてのお知らせ",
                related=f"<h3>{BOX}</h3>"),
        URL, SOURCE, CONFIG, diagnostics=diagnostics,
    )
    assert not cases and not releases and not alerts
    assert diagnostics == {"application_ended": 1}


@freeze_time("2026-10-01 10:00:00+09:00")
def test_open_deck_does_not_borrow_box_or_form_from_related_articles():
    diagnostics = {}
    cases, _, alerts = parse_retailer_lottery_detail(
        article(DECK, related=f'<h3>{BOX}</h3><a href="https://forms.gle/other">応募フォーム</a>'),
        URL, SOURCE, CONFIG, diagnostics=diagnostics,
    )
    assert not cases and not alerts
    assert diagnostics == {"excluded_product": 1}


@freeze_time("2026-10-01 10:00:00+09:00")
def test_open_box_does_not_borrow_closed_status_from_related_article():
    cases, _, alerts = parse_retailer_lottery_detail(
        article(related="<h3>受付終了【抽選販売】前回の抽選</h3>"), URL, SOURCE, CONFIG,
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].start_at.isoformat() == "2026-10-01"
    assert cases[0].end_at.isoformat() == "2026-10-03T12:00:00+09:00"
    assert cases[0].official_url == "https://docs.google.com/forms/d/e/current/viewform"


@freeze_time("2026-10-03 13:00:00+09:00")
def test_explicit_deadline_ends_draw_even_without_closed_heading():
    diagnostics = {}
    cases, _, alerts = parse_retailer_lottery_detail(
        article(), URL, SOURCE, CONFIG, diagnostics=diagnostics,
    )
    assert not cases and not alerts
    assert diagnostics == {"application_ended": 1}


@freeze_time("2026-10-01 10:00:00+09:00")
def test_genuine_unreadable_box_keeps_warning():
    html = article(product="ポケモンカードゲーム BOX抽選の対象は拡張パックです")
    # The category is mentioned outside a product heading/paragraph.
    html = html.replace(
        "<p>ポケモンカードゲーム BOX抽選の対象は拡張パックです</p>",
        "<div>ポケモンカードゲーム BOX抽選の対象は拡張パックです</div>",
    )
    cases, _, alerts = parse_retailer_lottery_detail(html, URL, SOURCE, CONFIG)
    assert not cases
    assert [alert.reason_code for alert in alerts] == ["retailer_box_product_missing"]
