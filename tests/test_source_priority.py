from __future__ import annotations

from datetime import date

from tcg_monitor.models import Release, SourceTier
from tcg_monitor.source_priority import merge_releases


def _release(
    source_tier: SourceTier,
    *,
    release_date: date | None = None,
    release_month: str | None = None,
) -> Release:
    return Release(
        "pokemon_card",
        '拡張パック「30th CELEBRATION」',
        "拡張パック",
        '拡張パック「30thCELEBRATION」',
        release_date,
        release_month,
        "https://www.pokemon-card.com/products/",
        "https://example.com/release-source",
        source_tier,
        "test",
        "high",
    ).with_id()


def test_exact_secondary_date_is_compatible_with_official_month() -> None:
    official = _release(SourceTier.OFFICIAL, release_month="2026-09")
    secondary = _release(
        SourceTier.SECONDARY,
        release_date=date(2026, 9, 16),
    )

    merged, alerts = merge_releases([secondary, official])

    assert merged == [official]
    assert alerts == []


def test_secondary_sources_do_not_impersonate_an_official_conflict() -> None:
    exact = _release(
        SourceTier.SECONDARY,
        release_date=date(2026, 9, 16),
    )
    month_only = _release(SourceTier.SECONDARY, release_month="2026-09")

    _, alerts = merge_releases([exact, month_only])

    assert alerts == []


def test_different_official_and_secondary_exact_dates_still_alert() -> None:
    official = _release(
        SourceTier.OFFICIAL,
        release_date=date(2026, 9, 16),
    )
    secondary = _release(
        SourceTier.SECONDARY,
        release_date=date(2026, 9, 18),
    )

    _, alerts = merge_releases([official, secondary])

    assert [alert.reason_code for alert in alerts] == [
        "secondary_official_conflict"
    ]
