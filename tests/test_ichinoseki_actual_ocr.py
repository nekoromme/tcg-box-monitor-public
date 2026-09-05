from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tcg_monitor.config import load_config
from tcg_monitor.japanese_datetime import parse_first_datetime, parse_period_start
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime


def test_ichinoseki_actual_ocr_does_not_break_primary_query():
    config = load_config("sites.yaml")
    source = next(s for s in config.sources if s.id == "yahoo_realtime_tsutaya_ichinoseki")
    status = "https://x.com/TSUTAYA19392430/status/2096124692696621430"
    html = f'''<div class="Tweet_TweetContainer__test"><p>
    ポケカ抽選販売のお知らせ 9月16日（水）発売
    抽選販売のWEB受付を開始します。申込にVポイントカードが必要です。
    30thセレブレーション 30thプレミアムスターターデッキ #ポケカ抽選</p>
    <img src="https://rts-pctr.c.yimg.jp/ichinoseki.jpg"><a href="{status}">投稿</a></div>'''
    cases, _, alerts = parse_yahoo_realtime(
        html, "https://search.yahoo.co.jp/realtime/search", source, config,
        date(2026, 9, 6), ocr_cache={status: Path(
            "tests/fixtures/ichinoseki_actual_20260905.txt",
        ).read_text()},
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].product_name == "拡張パック「30th CELEBRATION」"
    assert cases[0].start_at == date(2026, 9, 5)
    assert cases[0].end_at == datetime(2026, 9, 13, 23, 59, tzinfo=ZoneInfo("Asia/Tokyo"))


@pytest.mark.parametrize("text", [
    "79月5日", "2026年9月31日", "9/31 23:59", "9月5日29時99分", "2026年79月",
])
def test_invalid_ocr_date_returns_unknown_instead_of_aborting_source(text):
    result = parse_first_datetime(text, date(2026, 9, 5))
    assert result.value is None
    assert result.month_only is None
    assert result.warnings


def test_invalid_start_does_not_fall_forward_to_valid_deadline():
    result = parse_period_start("9月31日～10月3日23:59まで", date(2026, 9, 5))
    assert result.value is None
