from __future__ import annotations

from pathlib import Path

from tcg_monitor.models import SourceConfig

ALWAYS_ON_GROUP = "always"
TOHOKU_EXPEDITION_GROUP = "tohoku_expedition"
DEFAULT_SWITCH_PATH = "TOHOKU_EXPEDITION_MODE.txt"


class ExpeditionModeError(ValueError):
    """Raised when the deliberately simple expedition switch is malformed."""


def load_tohoku_expedition_mode(
    path: str | Path = DEFAULT_SWITCH_PATH,
) -> bool:
    """Read the human-facing ON/OFF switch.

    Comment and blank lines are ignored so the switch file can explain itself.
    Requiring exactly one ON/OFF token prevents a forgotten typo from silently
    enabling remote monitoring.
    """

    switch_path = Path(path)
    if not switch_path.is_file():
        raise ExpeditionModeError(
            f"{switch_path} がありません。東北遠征モードを安全に判定できません"
        )
    values = [
        line.split("#", 1)[0].strip().upper()
        for line in switch_path.read_text(encoding="utf-8").splitlines()
    ]
    values = [value for value in values if value]
    if values not in (["OFF"], ["ON"]):
        raise ExpeditionModeError(
            f"{switch_path} の最後の設定値を ON または OFF のどちらか一つにしてください"
        )
    return values[0] == "ON"


def tohoku_expedition_label(enabled: bool) -> str:
    return "ON" if enabled else "OFF"


def active_source_filter(
    sources: list[SourceConfig],
    requested_source_ids: set[str] | None,
    *,
    tohoku_expedition_enabled: bool,
) -> set[str]:
    """Return source IDs that may reach the network in this run."""

    allowed = {
        source.id
        for source in sources
        if source.enabled
        and (
            source.activation_group == ALWAYS_ON_GROUP
            or (
                tohoku_expedition_enabled
                and source.activation_group == TOHOKU_EXPEDITION_GROUP
            )
        )
    }
    if requested_source_ids is None:
        return allowed
    return requested_source_ids & allowed
