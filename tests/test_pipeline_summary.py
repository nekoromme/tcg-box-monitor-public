from tcg_monitor.config import load_config
from tcg_monitor.pipeline import _healthy_fallbacks, _monitor_outcome_counts


def test_monitor_outcome_counts_are_mutually_exclusive() -> None:
    source_outcomes = {
        "healthy": True,
        "partially_degraded": True,
        "failed_but_covered": False,
        "failed": False,
    }
    covered_sources = {
        "partially_degraded": ["fallback_a"],
        "failed_but_covered": ["fallback_b"],
        "not_executed": ["fallback_c"],
    }

    assert _monitor_outcome_counts(source_outcomes, covered_sources) == (1, 2, 1)


def test_pokemon_official_failure_uses_verified_release_fallback() -> None:
    config = load_config("sites.yaml")
    source_outcomes = {source.id: True for source in config.sources}
    source_outcomes["pokemon_official_products"] = False

    covered_sources = _healthy_fallbacks(config, source_outcomes)

    assert covered_sources["pokemon_official_products"] == ["snkrdunk_pokemon"]
    assert _monitor_outcome_counts(source_outcomes, covered_sources) == (
        len(source_outcomes) - 1,
        1,
        0,
    )
