from __future__ import annotations

from pathlib import Path

import pytest

from tcg_monitor.expedition_mode import ExpeditionModeError, load_expedition_mode


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("ON", True), ("OFF", False), ("on", True), ("off", False)],
)
def test_load_expedition_mode(tmp_path: Path, mode: str, expected: bool) -> None:
    path = tmp_path / "EXPEDITION_MODE.txt"
    path.write_text(
        "# コメントは無視されます\n"
        f"EXPEDITION_MODE={mode}\n",
        encoding="utf-8",
    )

    assert load_expedition_mode(path) is expected


@pytest.mark.parametrize(
    "content",
    [
        "",
        "ON\n",
        "EXPEDITION_MODE=MAYBE\n",
        "UNKNOWN=OFF\n",
        "EXPEDITION_MODE=OFF\nEXPEDITION_MODE=ON\n",
    ],
)
def test_invalid_expedition_mode_fails_closed(
    tmp_path: Path,
    content: str,
) -> None:
    path = tmp_path / "EXPEDITION_MODE.txt"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ExpeditionModeError):
        load_expedition_mode(path)


def test_missing_expedition_mode_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ExpeditionModeError):
        load_expedition_mode(tmp_path / "missing.txt")
