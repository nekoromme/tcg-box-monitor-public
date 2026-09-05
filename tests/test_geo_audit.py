from datetime import datetime
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from tcg_monitor.config import load_config
from tcg_monitor.parsers.generic import discover_geo_news_urls, parse_generic

CONFIG = load_config("sites.yaml")
SOURCE = next(s for s in CONFIG.sources if s.id == "geo")
URL = "https://geo-online.co.jp/news/779"
HTML = '''<title>ゲオ抽選販売</title><main><h1>
9月16日発売 ポケモンカードゲーム MEGA 拡張パック『30th CELEBRATION』他 抽選販売
</h1><p>拡張パック『30th CELEBRATION』と『プレミアムデッキセット』の抽選販売。</p>
<p>応募期間は「8/31(月) 11:00 ～ 9/3(木) 17:59」までとなります。</p>
<p>購入時の本人確認に必要な書類</p></main><footer>キャンペーン・大会・DVD BOX</footer>'''


def test_geo_index_accepts_whitespace_variant_but_not_unrelated_host():
    html = '''<a href="/news/780">遊戯王 ORIGINAL ARTWORKCOLLECTION 抽選販売</a>
    <a href="https://evil.example/news/780">遊戯王 ORIGINAL ARTWORK COLLECTION 抽選販売</a>'''
    assert discover_geo_news_urls(html, "https://geo-online.co.jp/news/", SOURCE, CONFIG) == [
        "https://geo-online.co.jp/news/780",
    ]


@freeze_time("2026-08-31 12:00:00+09:00")
def test_geo_mixed_deck_and_footer_do_not_hide_named_box():
    cases, _, alerts = parse_generic(HTML, URL, SOURCE, CONFIG)
    assert not alerts
    assert len(cases) == 1
    assert cases[0].product_name == "拡張パック「30th CELEBRATION」"
    assert cases[0].start_at == datetime(2026, 8, 31, 11, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert cases[0].end_at == datetime(2026, 9, 3, 17, 59, tzinfo=ZoneInfo("Asia/Tokyo"))


@freeze_time("2026-09-06 00:00:00+09:00")
def test_geo_real_ended_period_is_verified_without_new_notification():
    diagnostics = {}
    cases, _, alerts = parse_generic(HTML, URL, SOURCE, CONFIG, diagnostics)
    assert not cases and not alerts
    assert diagnostics == {
        "validated_product": 1, "validated_application_period": 1, "application_ended": 1,
    }


@freeze_time("2026-08-31 12:00:00+09:00")
def test_geo_deck_heading_does_not_borrow_box_from_related_news():
    html = '''<h1>ポケモンカードゲーム プレミアムデッキセット 抽選販売</h1>
    <p>応募期間8/31 11:00～9/3 17:59まで</p>
    <footer>ポケモンカードゲーム 拡張パック『30th CELEBRATION』1BOX</footer>'''
    assert not parse_generic(html, URL, SOURCE, CONFIG)[0]
