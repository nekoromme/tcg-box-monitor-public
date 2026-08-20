from datetime import date, datetime
from zoneinfo import ZoneInfo

from tcg_monitor.japanese_datetime import parse_first_datetime, parse_period_start


def test_date_only_range_start_beats_timed_deadline() -> None:
    parsed = parse_first_datetime(
        "8月7日（金）～8月10日（月）21時まで",
        date(2026, 8, 7),
    )

    assert parsed.value == date(2026, 8, 7)
    assert not parsed.warnings


def test_slash_date_only_range_start_beats_timed_deadline() -> None:
    parsed = parse_first_datetime(
        "8/7～8/10 21:00まで",
        date(2026, 8, 7),
    )

    assert parsed.value == date(2026, 8, 7)


def test_timed_range_start_keeps_its_start_time() -> None:
    parsed = parse_first_datetime(
        "8月7日（金）10時～8月10日（月）21時まで",
        date(2026, 8, 7),
    )

    assert parsed.value == datetime(
        2026,
        8,
        7,
        10,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )


def test_period_with_only_a_deadline_has_no_start() -> None:
    parsed = parse_period_start(
        "7月29日（水）23:59まで",
        date(2026, 7, 4),
    )

    assert parsed.value is None
    assert parsed.warnings == ("application_deadline_without_start",)


def test_period_range_remains_valid() -> None:
    parsed = parse_period_start(
        "7月25日（土）10:00～7月29日（水）23:59まで",
        date(2026, 7, 25),
    )

    assert parsed.value == datetime(
        2026,
        7,
        25,
        10,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )


def test_ocr_damaged_range_with_two_dates_remains_valid() -> None:
    parsed = parse_period_start(
        "7月25日（土）10:00て7月29日（水）23:59まで",
        date(2026, 7, 25),
    )

    assert parsed.value == datetime(
        2026,
        7,
        25,
        10,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )
