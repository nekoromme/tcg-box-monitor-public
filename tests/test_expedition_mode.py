from __future__ import annotations

from pathlib import Path

import pytest

from tcg_monitor.expedition_mode import ExpeditionModeError, load_expedition_modes
from tcg_monitor.source_groups import (
    EXPEDITION_SENDAI_GROUP,
    EXPEDITION_TOKYO_GROUP,
    EXPEDITION_TOKYO_ROUTE_GROUP,
)


@pytest.mark.parametrize(
    ("sendai", "route", "tokyo", "expected"),
    [
        ("ON", "OFF", "on", {EXPEDITION_SENDAI_GROUP, EXPEDITION_TOKYO_GROUP}),
        ("off", "ON", "OFF", {EXPEDITION_TOKYO_ROUTE_GROUP}),
        (
            "ON",
            "ON",
            "ON",
            {
                EXPEDITION_SENDAI_GROUP,
                EXPEDITION_TOKYO_ROUTE_GROUP,
                EXPEDITION_TOKYO_GROUP,
            },
        ),
    ],
)
def test_load_expedition_modes(
    tmp_path: Path,
    sendai: str,
    route: str,
    tokyo: str,
    expected: set[str],
) -> None:
    path = tmp_path / "EXPEDITION_MODE.txt"
    path.write_text(
        "# コメントは無視されます\n"
        f"EXPEDITION_SENDAI={sendai}\n"
        f"EXPEDITION_TOKYO_ROUTE={route}\n"
        f"EXPEDITION_TOKYO={tokyo}\n",
        encoding="utf-8",
    )

    assert load_expedition_modes(path).enabled_groups == expected


@pytest.mark.parametrize(
    "content",
    [
        "",
        "ON\n",
        "EXPEDITION_SENDAI=MAYBE\n",
        "UNKNOWN=OFF\n",
        (
            "EXPEDITION_SENDAI=OFF\n"
            "EXPEDITION_SENDAI=ON\n"
            "EXPEDITION_TOKYO_ROUTE=OFF\n"
            "EXPEDITION_TOKYO=OFF\n"
        ),
        "EXPEDITION_SENDAI=OFF\nEXPEDITION_TOKYO=OFF\n",
    ],
)
def test_invalid_expedition_mode_fails_closed(
    tmp_path: Path,
    content: str,
) -> None:
    path = tmp_path / "EXPEDITION_MODE.txt"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ExpeditionModeError):
        load_expedition_modes(path)


def test_missing_expedition_mode_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ExpeditionModeError):
        load_expedition_modes(tmp_path / "missing.txt")
