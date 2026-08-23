from datetime import date

from tcg_monitor.cli import _lottery_date_in_delivery_window


def test_new_lottery_detected_one_day_late_is_still_delivered() -> None:
    assert _lottery_date_in_delivery_window(
        date(2026, 8, 7),
        date(2026, 8, 8),
        date(2027, 8, 8),
    )


def test_new_lottery_older_than_grace_period_is_not_backfilled() -> None:
    assert not _lottery_date_in_delivery_window(
        date(2026, 8, 6),
        date(2026, 8, 8),
        date(2027, 8, 8),
    )


def test_future_limit_still_applies_to_late_delivery_window() -> None:
    assert not _lottery_date_in_delivery_window(
        date(2027, 8, 9),
        date(2026, 8, 8),
        date(2027, 8, 8),
    )


def test_negative_grace_does_not_expand_into_the_past() -> None:
    assert not _lottery_date_in_delivery_window(
        date(2026, 8, 7),
        date(2026, 8, 8),
        date(2027, 8, 8),
        late_grace_days=-1,
    )
