from __future__ import annotations

from pathlib import Path

DEFAULT_EXPEDITION_MODE_PATH = "EXPEDITION_MODE.txt"
_SETTING_NAME = "EXPEDITION_MODE"


class ExpeditionModeError(ValueError):
    """Raised when the deliberately simple expedition switch is malformed."""


def load_expedition_mode(
    path: str | Path = DEFAULT_EXPEDITION_MODE_PATH,
) -> bool:
    """Return whether the additional one-visit expedition sources are enabled.

    The switch deliberately fails closed. A missing or malformed file must stop
    the run instead of accidentally fetching distant stores.
    """

    switch_path = Path(path)
    if not switch_path.is_file():
        raise ExpeditionModeError(
            f"{switch_path} がありません。遠征監視を安全に判定できません"
        )

    enabled: bool | None = None
    for line_number, raw_line in enumerate(
        switch_path.read_text(encoding="utf-8").splitlines(),
        1,
    ):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" not in line:
            raise ExpeditionModeError(
                f"{switch_path}:{line_number} は EXPEDITION_MODE=ON または OFF "
                "の形式にしてください"
            )
        key, raw_mode = (part.strip() for part in line.split("=", 1))
        if key != _SETTING_NAME:
            raise ExpeditionModeError(
                f"{switch_path}:{line_number} に未知の設定があります: {key}"
            )
        if enabled is not None:
            raise ExpeditionModeError(
                f"{switch_path}:{line_number} で EXPEDITION_MODE が重複しています"
            )
        mode = raw_mode.upper()
        if mode not in {"ON", "OFF"}:
            raise ExpeditionModeError(
                f"{switch_path}:{line_number} は EXPEDITION_MODE=ON または OFF "
                "にしてください"
            )
        enabled = mode == "ON"

    if enabled is None:
        raise ExpeditionModeError(
            f"{switch_path} に EXPEDITION_MODE=ON または OFF がありません"
        )
    return enabled
