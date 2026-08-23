from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from tcg_monitor.cli import _baseline_newly_enabled_lotteries
from tcg_monitor.config import load_config
from tcg_monitor.game_modes import GameModeError, load_enabled_game_ids
from tcg_monitor.models import LotteryCase, SourceTier
from tcg_monitor.pipeline import run_pipeline
from tcg_monitor.state import MonitorState


def test_game_switch_requires_one_explicit_value_per_game(tmp_path: Path) -> None:
    switch = tmp_path / "GAME_MONITOR_MODES.txt"
    switch.write_text(
        "# 作品別\n"
        "pokemon_card=ON\n"
        "one_piece_card=OFF\n"
        "dragon_ball_fusion_world=ON\n"
        "yu_gi_oh=OFF\n"
        "lorcana=ON  # 有効\n",
        encoding="utf-8",
    )

    enabled = load_enabled_game_ids(
        {
            "pokemon_card",
            "one_piece_card",
            "dragon_ball_fusion_world",
            "yu_gi_oh",
            "lorcana",
        },
        switch,
    )
    assert enabled == {
        "pokemon_card",
        "dragon_ball_fusion_world",
        "lorcana",
    }


@pytest.mark.parametrize(
    "body",
    [
        "pokemon_card=ON\n",
        "pokemon_card=YES\n",
        "pokemon_card=ON\npokemon_card=OFF\n",
        "unknown_game=ON\n",
    ],
)
def test_game_switch_fails_closed_on_incomplete_or_bad_values(
    tmp_path: Path,
    body: str,
) -> None:
    switch = tmp_path / "GAME_MONITOR_MODES.txt"
    switch.write_text(body, encoding="utf-8")
    with pytest.raises(GameModeError):
        load_enabled_game_ids({"pokemon_card", "one_piece_card"}, switch)


def test_off_games_skip_their_sources_before_fetching() -> None:
    config = replace(
        load_config("sites.yaml"),
        enabled_game_ids=frozenset({"pokemon_card"}),
    )

    cases, releases, alerts = run_pipeline(
        config,
        "tests/fixtures",
        {"yugioh_official_products", "lorcana_official_products"},
    )

    assert not cases
    assert not releases
    assert not alerts


def test_newly_enabled_game_baselines_visible_lotteries_without_calendar(
    tmp_path: Path,
) -> None:
    state = MonitorState.load(tmp_path / "monitor_state.json")
    case = LotteryCase(
        "yu_gi_oh",
        "hobby_station",
        "ホビーステーション",
        "基本パック「テスト」",
        "基本パック",
        "test",
        date(2026, 8, 20),
        "https://example.com/apply",
        "https://example.com/source",
        SourceTier.OFFICIAL,
        "test",
        "high",
    ).with_id()

    baseline_ids = _baseline_newly_enabled_lotteries(
        state,
        [case],
        frozenset({"yu_gi_oh"}),
    )

    assert baseline_ids == {case.case_id}
    assert case.case_id in state.data["seen_cases"]
    assert state.delivered(f"lottery:started:{case.case_id}")
    assert f"lottery:{case.case_id}" not in state.data["calendar_sync"]
