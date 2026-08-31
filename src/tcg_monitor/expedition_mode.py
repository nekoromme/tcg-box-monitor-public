from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tcg_monitor.source_groups import (
    EXPEDITION_SENDAI_GROUP,
    EXPEDITION_TOKYO_GROUP,
    EXPEDITION_TOKYO_ROUTE_GROUP,
)

DEFAULT_EXPEDITION_MODE_PATH = "EXPEDITION_MODE.txt"
_SETTING_TO_GROUP = {
    "EXPEDITION_SENDAI": EXPEDITION_SENDAI_GROUP,
    "EXPEDITION_TOKYO_ROUTE": EXPEDITION_TOKYO_ROUTE_GROUP,
    "EXPEDITION_TOKYO": EXPEDITION_TOKYO_GROUP,
}


class ExpeditionModeError(ValueError):
    """Raised when the deliberately simple expedition switch is malformed."""


@dataclass(frozen=True)
class ExpeditionModes:
    """The three independently switchable expedition areas."""

    sendai: bool
    tokyo_route: bool
    tokyo: bool

    @property
    def enabled_groups(self) -> frozenset[str]:
        pairs = (
            (EXPEDITION_SENDAI_GROUP, self.sendai),
            (EXPEDITION_TOKYO_ROUTE_GROUP, self.tokyo_route),
            (EXPEDITION_TOKYO_GROUP, self.tokyo),
        )
        return frozenset(group for group, enabled in pairs if enabled)


def load_expedition_modes(
    path: str | Path = DEFAULT_EXPEDITION_MODE_PATH,
) -> ExpeditionModes:
    """Load the three one-visit expedition switches.

    The switch deliberately fails closed. A missing or malformed file must stop
    the run instead of accidentally fetching distant stores.
    """

    switch_path = Path(path)
    if not switch_path.is_file():
        raise ExpeditionModeError(
            f"{switch_path} がありません。遠征監視を安全に判定できません"
        )

    values: dict[str, bool] = {}
    for line_number, raw_line in enumerate(
        switch_path.read_text(encoding="utf-8").splitlines(),
        1,
    ):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" not in line:
            raise ExpeditionModeError(
                f"{switch_path}:{line_number} は 設定名=ON または OFF "
                "の形式にしてください"
            )
        key, raw_mode = (part.strip() for part in line.split("=", 1))
        if key not in _SETTING_TO_GROUP:
            raise ExpeditionModeError(
                f"{switch_path}:{line_number} に未知の設定があります: {key}"
            )
        if key in values:
            raise ExpeditionModeError(
                f"{switch_path}:{line_number} で {key} が重複しています"
            )
        mode = raw_mode.upper()
        if mode not in {"ON", "OFF"}:
            raise ExpeditionModeError(
                f"{switch_path}:{line_number} は {key}=ON または OFF にしてください"
            )
        values[key] = mode == "ON"

    missing = set(_SETTING_TO_GROUP) - set(values)
    if missing:
        raise ExpeditionModeError(
            f"{switch_path} に次の設定がありません: {', '.join(sorted(missing))}"
        )
    return ExpeditionModes(
        sendai=values["EXPEDITION_SENDAI"],
        tokyo_route=values["EXPEDITION_TOKYO_ROUTE"],
        tokyo=values["EXPEDITION_TOKYO"],
    )
