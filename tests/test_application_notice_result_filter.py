"""受付告知の注意書きを、当選結果の投稿と取り違えないための再現テスト。"""

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tcg_monitor.config import load_config
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime

ROOT = Path(__file__).resolve().parents[1]
STATUS = "https://x.com/example_store/status/2098969926967197932"
BODY = """2026年9月26日発売、遊戯王OCG「ORIGINAL ARTWORK COLLECTION」抽選販売。
詳しい応募方法と日程は画像を確認してください。"""
# 公開するテストは一般化した告知のみ。調査に使った画像読取原文は含めない。
NOTICE = """遊戯王OCG ORIGINAL ARTWORK COLLECTION 抽選販売
抽選期間：2026年9月13日(日)12:00頃から9月19日(土)23:59頃まで
当選発表：2026年9月20日(日)から9月21日(月)の間予定
販売期間：2026年9月26日(土)から9月27日(日)まで
当選者本人の本人確認書類が必要です。"""


def parse_notice(ocr_text: str, detected: date = date(2026, 9, 13)):
    config = load_config(ROOT / "sites.yaml")
    source = next(s for s in config.sources if s.id == "yahoo_realtime_tsutaya_akebono")
    source = replace(source, parser_options={
        **source.parser_options, "account": "example_store",
        "retailer_id": "test_store", "retailer_name": "テスト店舗",
    })
    html = f'''<div class="Tweet_TweetContainer__test">
    <p class="Tweet_body__test">{BODY}</p>
    <img src="https://rts-pctr.c.yimg.jp/notice.jpg">
    <time><a href="{STATUS}">9月13日</a></time></div>'''
    diagnostics: dict[str, int] = {}
    cases, _, alerts = parse_yahoo_realtime(
        html, source.discovery_urls[0], source, config, detected,
        ocr_cache={STATUS: ocr_text}, diagnostics=diagnostics,
    )
    return cases, alerts, diagnostics


def test_application_period_with_winner_instructions():
    # 発売日・当選発表日を開始日にしない。
    cases, alerts, _ = parse_notice(NOTICE)
    assert not alerts
    assert len(cases) == 1
    assert cases[0].game_id == "yu_gi_oh"
    assert "ORIGINAL ARTWORK COLLECTION" in cases[0].product_name
    assert cases[0].start_at == datetime(2026, 9, 13, 12, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert cases[0].end_at == datetime(2026, 9, 19, 23, 59, tzinfo=ZoneInfo("Asia/Tokyo"))


@pytest.mark.parametrize("label", ["抽選期間", "抽選申込期間", "エントリー期間", "応募期間"])
def test_supported_period_labels_with_winner_instructions(label):
    cases, alerts, _ = parse_notice(
        f"{label}：2026年9月13日12:00から9月19日23:59まで\n"
        "当選発表：9月20日。当選者本人の本人確認書類が必要です。"
    )
    assert not alerts
    assert len(cases) == 1


@pytest.mark.parametrize("period", [
    "", "抽選期間：2026年9月5日12:00から9月19日23:59まで",
    "販売期間：2026年9月26日12:00から9月27日23:59まで",
])
def test_result_notice_without_fresh_application_start_stays_excluded(period):
    cases, _, diagnostics = parse_notice(f"当選発表：9月13日。当選者本人のみ購入可能。{period}")
    assert not cases
    assert diagnostics.get("closed_or_result_notice") == 1


def test_expired_application_is_not_revived_by_fix():
    cases, _, diagnostics = parse_notice(NOTICE, date(2026, 9, 20))
    assert not cases
    assert diagnostics.get("application_ended") == 1
