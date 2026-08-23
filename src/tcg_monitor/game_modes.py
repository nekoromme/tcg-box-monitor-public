from __future__ import annotations

from pathlib import Path

DEFAULT_GAME_MODES_PATH = "GAME_MONITOR_MODES.txt"
LEGACY_ENABLED_GAME_IDS = frozenset(
    {
        "pokemon_card",
        "one_piece_card",
        "dragon_ball_fusion_world",
    }
)


class GameModeError(ValueError):
    """Raised when the deliberately simple per-game switch is malformed."""


def load_enabled_game_ids(
    known_game_ids: set[str] | frozenset[str],
    path: str | Path = DEFAULT_GAME_MODES_PATH,
) -> frozenset[str]:
    """Read one explicit ``game_id=ON|OFF`` setting for every known game.

    Missing, duplicate and unknown entries are errors.  Failing closed here is
    preferable to silently fetching or notifying for an unintended title.
    """

    switch_path = Path(path)
    if not switch_path.is_file():
        raise GameModeError(
            f"{switch_path} がありません。作品別の監視状態を安全に判定できません"
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
            raise GameModeError(
                f"{switch_path}:{line_number} は game_id=ON または OFF の形式にしてください"
            )
        game_id, raw_mode = (part.strip() for part in line.split("=", 1))
        if game_id not in known_game_ids:
            raise GameModeError(
                f"{switch_path}:{line_number} に未知の作品IDがあります: {game_id}"
            )
        if game_id in values:
            raise GameModeError(
                f"{switch_path}:{line_number} で作品IDが重複しています: {game_id}"
            )
        mode = raw_mode.upper()
        if mode not in {"ON", "OFF"}:
            raise GameModeError(
                f"{switch_path}:{line_number} の {game_id} は ON または OFF にしてください"
            )
        values[game_id] = mode == "ON"

    missing = known_game_ids - values.keys()
    if missing:
        raise GameModeError(
            f"{switch_path} に設定がない作品があります: {', '.join(sorted(missing))}"
        )
    return frozenset(game_id for game_id, enabled in values.items() if enabled)
