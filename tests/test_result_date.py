from datetime import date, datetime
from zoneinfo import ZoneInfo

from tcg_monitor.result_date import published_result_date


def test_result_date_follows_explicit_label_and_keeps_time() -> None:
    text = "応募期間 2026年9月20日～9月24日\n結果発表：9月28日 12:00"
    assert published_result_date(text, date(2026, 9, 20), date(2026, 9, 24)) == datetime(
        2026, 9, 28, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo")
    )


def test_result_date_never_borrows_release_or_application_date() -> None:
    assert published_result_date(
        "当選発表予定日は後日案内。発売日2026年9月28日",
        date(2026, 9, 20),
    ) is None
    assert published_result_date(
        "抽選結果発表 9月19日。応募期間 9月20日～9月24日",
        date(2026, 9, 20),
    ) is None
