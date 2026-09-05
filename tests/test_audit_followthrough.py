from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from tcg_monitor.cli import _cleanup_confirmed_false_positive_cases
from tcg_monitor.config import load_config
from tcg_monitor.google_calendar import CalendarAdapter
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.parsers.retailer_lottery import discover_retailer_lottery_urls
from tcg_monitor.state import MonitorState

CONFIG = load_config("sites.yaml")


def source(source_id):
    return next(s for s in CONFIG.sources if s.id == source_id)


def test_chomeigaoka_mixed_product_with_actual_cached_ocr():
    status = "https://x.com/TBSSENDAICHOMEI/status/2095728630328631341"
    html = f'''<div class="Tweet_TweetContainer__test"><p>
    ポケモンカードゲーム 拡張パック 30th CELEBRATION プレミアムデッキセット
    抽選販売のお知らせ。詳細は画像をご確認ください。</p>
    <img src="https://pbs.twimg.com/media/chomei.jpg"><a href="{status}">投稿</a></div>'''
    ocr = Path("tests/fixtures/chomeigaoka_mixed_20260904.txt").read_text()
    diagnostics = {}
    cases, _, _ = parse_yahoo_realtime(
        html, "https://search.yahoo.co.jp/realtime/search",
        source("yahoo_realtime_tsutaya_chomeigaoka"), CONFIG, date(2026, 9, 5),
        ocr_cache={status: ocr}, diagnostics=diagnostics,
    )
    assert len(cases) == 1, diagnostics
    assert "デッキ" not in cases[0].product_name
    assert "30th" in cases[0].product_name
    assert cases[0].start_at == date(2026, 9, 4)


@pytest.mark.parametrize("condition", [
    "いいねとリポストで抽選予約可能です", "応募にはこのポストのリポストが必要です",
    "応募条件：このポストをリポスト", "抽選参加方法 X: いいねとリボスト",
    "応募は店頭に掲示されたQRコードから",
])
@pytest.mark.parametrize("in_image", [True, False])
def test_application_conditions_checked_in_both_body_and_image(condition, in_image):
    status = "https://x.com/santycrissroad/status/2095747915730051152"
    body = "ポケモンカードゲーム 拡張パック「30th CELEBRATION」抽選予約受付開始"
    html = f'''<div class="Tweet_TweetContainer__test"><p>
    {body} {'' if in_image else condition}</p>
    <img src="https://pbs.twimg.com/media/conditions.jpg"><a href="{status}">投稿</a></div>'''
    diagnostics = {}
    cases, _, _ = parse_yahoo_realtime(
        html, "https://search.yahoo.co.jp/realtime/search", source("yahoo_realtime_santy_sendai"),
        CONFIG, date(2026, 9, 5), ocr_cache={status: condition if in_image else ""},
        diagnostics=diagnostics,
    )
    assert not cases
    assert diagnostics["disallowed_application"] == 1


def test_itoyokado_follows_campaign_pages_without_leaving_official_host():
    root = "https://iyec.itoyokado.co.jp/shop/e/eE4reslot/"
    html = '''<a href="/shop/pages/apply_pomega_04.aspx">ポケモンカード 拡張パック 抽選</a>
    <a href="https://evil.example/shop/pages/apply_pomega_04.aspx">ポケモンカード BOX 抽選</a>
    <a href="/shop/pages/privacy.aspx">個人情報</a>'''
    urls = discover_retailer_lottery_urls(html, root, source("itoyokado_online_lottery"), CONFIG)
    assert urls == ["https://iyec.itoyokado.co.jp/shop/pages/apply_pomega_04.aspx"]


def test_cleanup_only_exact_santy_false_positive(tmp_path):
    case_id = "b0a6499b53846c03ca6bde6287300c5d072e390c2b9ae8ebed41c8175a95620b"
    expected = CONFIG.system["runtime"]["confirmed_false_positive_cases"][case_id]
    state = MonitorState.load(tmp_path / "state.json")
    state.data["seen_cases"] = {case_id: dict(expected), "keep": {"retailer_id": "other"}}
    state.data["calendar_sync"] = {f"lottery:{case_id}": {"event_id": expected["event_id"]}}
    calendar = MagicMock(spec=CalendarAdapter)
    calendar.delete_owned_event.return_value = {"status": "deleted"}
    result = _cleanup_confirmed_false_positive_cases(state, calendar, {case_id: expected})
    assert result[0]["status"] == "deleted"
    calendar.delete_owned_event.assert_called_once_with(
        expected["event_id"], kind="lottery", internal_id=case_id,
    )
    assert list(state.data["seen_cases"]) == ["keep"]


def test_higashi_sendai_recovers_date_from_actual_ocr_not_deadline():
    status = "https://x.com/YTHtoreka/status/2096172988940874205"
    html = f'''<div class="Tweet_TweetContainer__test"><p>
    【抽選販売】ワンピースカード再入荷商品の抽選販売をいたします。
    抽選はLivePocketを使用いたします。注意事項ご確認の上お申込みください。</p>
    <img src="https://pbs.twimg.com/media/higashi.jpg"><a href="{status}">投稿</a></div>'''
    ocr = Path("tests/fixtures/higashi_sendai_20260905.txt").read_text()
    diagnostics = {}
    cases, _, alerts = parse_yahoo_realtime(
        html, "https://search.yahoo.co.jp/realtime/search",
        source("yahoo_realtime_tsutaya_higashi_sendai"), CONFIG, date(2026, 9, 5),
        ocr_cache={status: ocr}, diagnostics=diagnostics,
    )
    assert len(cases) == 1, (diagnostics, alerts)
    assert cases[0].start_at == datetime(2026, 9, 5, 19, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert cases[0].end_at == datetime(2026, 9, 7, 22, tzinfo=ZoneInfo("Asia/Tokyo"))
