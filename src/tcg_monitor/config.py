from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - environment fallback
    yaml = None

from tcg_monitor.expedition import (
    ALWAYS_ON_GROUP,
    TOHOKU_EXPEDITION_GROUP,
)
from tcg_monitor.models import (
    Config,
    GameConfig,
    GameId,
    GameSupport,
    LotteryStartPolicy,
    RenderMode,
    SourceConfig,
    SourceTier,
)


def _load_yaml(path: Path) -> dict[str, Any]:
    if yaml is not None:
        return dict(yaml.safe_load(path.read_text(encoding="utf-8")))
    script = "require 'yaml'; require 'json'; puts YAML.load_file(ARGV[0]).to_json"
    out = subprocess.check_output(["ruby", "-e", script, str(path)], text=True)
    return dict(json.loads(out))


class ConfigError(ValueError):
    pass


_ALLOWED_ACTIVATION_GROUPS = {
    ALWAYS_ON_GROUP,
    TOHOKU_EXPEDITION_GROUP,
}


def _list(v: Any) -> list[str]:
    return list(v or [])


def _validated_system(raw_system: Any) -> dict[str, Any]:
    if not isinstance(raw_system, dict):
        raise ConfigError("system must be a mapping")
    system = dict(raw_system)
    for name in ("request_timeout_seconds", "request_budget_seconds"):
        value = system.get(name)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ConfigError(f"{name} must be greater than zero")
    minimum_interval = system.get("minimum_host_interval_seconds")
    if minimum_interval is not None and (
        isinstance(minimum_interval, bool)
        or not isinstance(minimum_interval, (int, float))
        or minimum_interval < 0
    ):
        raise ConfigError("minimum_host_interval_seconds must not be negative")
    max_retries = system.get("max_retries")
    if max_retries is not None and (
        isinstance(max_retries, bool)
        or not isinstance(max_retries, int)
        or max_retries < 0
    ):
        raise ConfigError("max_retries must be a non-negative integer")
    max_parallel_hosts = system.get("max_parallel_hosts")
    if max_parallel_hosts is not None and (
        isinstance(max_parallel_hosts, bool)
        or not isinstance(max_parallel_hosts, int)
        or not 1 <= max_parallel_hosts <= 16
    ):
        raise ConfigError("max_parallel_hosts must be an integer from 1 to 16")
    backoffs = system.get("retry_backoff_seconds")
    if backoffs is not None and (
        not isinstance(backoffs, list)
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value < 0
            for value in backoffs
        )
    ):
        raise ConfigError("retry_backoff_seconds must be a list of non-negative numbers")
    return system


def _validate_fallback_sources(sources: list[SourceConfig]) -> None:
    """Validate explicit alternatives used to judge end-to-end coverage.

    A failed primary source may be reported as degraded instead of unavailable
    only when every verified game still has a healthy configured alternative.
    Keeping these relationships in configuration prevents alert suppression
    from silently depending on source names or comments.
    """

    by_id = {source.id: source for source in sources}
    for source in sources:
        if len(source.fallback_source_ids) != len(set(source.fallback_source_ids)):
            raise ConfigError(f"duplicate fallback source: {source.id}")
        for fallback_id in source.fallback_source_ids:
            if fallback_id == source.id:
                raise ConfigError(f"source cannot fall back to itself: {source.id}")
            fallback = by_id.get(fallback_id)
            if fallback is None:
                raise ConfigError(
                    f"unknown fallback source: {source.id}:{fallback_id}"
                )
            if not fallback.enabled:
                raise ConfigError(
                    f"fallback source must be enabled: {source.id}:{fallback_id}"
                )

        verified_games = {
            game_id
            for game_id, status in source.supported_games.items()
            if status == GameSupport.VERIFIED
        }
        covered_games = {
            game_id
            for game_id in verified_games
            if any(
                by_id[fallback_id].supported_games.get(game_id)
                == GameSupport.VERIFIED
                for fallback_id in source.fallback_source_ids
            )
        }
        missing_games = verified_games - covered_games
        if source.fallback_source_ids and missing_games:
            missing = ", ".join(sorted(missing_games))
            raise ConfigError(
                f"fallback sources do not cover verified games: {source.id}:{missing}"
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(source_id: str) -> None:
        if source_id in visited:
            return
        if source_id in visiting:
            raise ConfigError(f"fallback source cycle detected: {source_id}")
        visiting.add(source_id)
        for fallback_id in by_id[source_id].fallback_source_ids:
            visit(fallback_id)
        visiting.remove(source_id)
        visited.add(source_id)

    for source_id in by_id:
        visit(source_id)


def load_config(path: str | Path = "sites.yaml") -> Config:
    raw = _load_yaml(Path(path))
    if raw.get("schema_version") != 2:
        raise ConfigError("sites.yaml schema_version must be 2")
    system = _validated_system(raw.get("system", {}))
    games: dict[str, GameConfig] = {}
    for gid, g in raw["games"].items():
        games[gid] = GameConfig(
            id=GameId(gid),
            name=g["name"],
            short_name=g["short_name"],
            release_notification_prefix=g["release_notification_prefix"],
            release_calendar_prefix=g["release_calendar_prefix"],
            lottery_schedule_prefix=g["lottery_schedule_prefix"],
            lottery_start_prefix=g["lottery_start_prefix"],
            include_keywords=_list(g.get("include_keywords")),
            box_product_keywords=_list(g.get("box_product_keywords")),
            box_evidence_patterns=_list(g.get("box_evidence_patterns")),
            product_exclude_keywords=_list(g.get("product_exclude_keywords")),
            product_code_patterns=_list(g.get("product_code_patterns")),
        )
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    sources: list[SourceConfig] = []
    for s in raw.get("sources", []):
        if s["id"] in seen_ids:
            raise ConfigError(f"duplicate source id: {s['id']}")
        seen_ids.add(s["id"])
        tier = SourceTier(s["source_tier"])
        supported_games: dict[str, GameSupport] = {}
        raw_supported_games = s.get("supported_games", {})
        if not isinstance(raw_supported_games, dict):
            raise ConfigError(f"supported_games must be a mapping: {s['id']}")
        for game_id, raw_status in raw_supported_games.items():
            if game_id not in games:
                raise ConfigError(f"unknown supported game: {s['id']}:{game_id}")
            try:
                supported_games[str(game_id)] = GameSupport(str(raw_status))
            except ValueError as exc:
                allowed = ", ".join(status.value for status in GameSupport)
                raise ConfigError(
                    f"bad supported_games status: {s['id']}:{game_id}={raw_status}; "
                    f"allowed={allowed}"
                ) from exc
        for url in s.get("discovery_urls", []):
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ConfigError(f"invalid url: {url}")
            key = f"{s['id']}|{url}"
            if key in seen_urls:
                raise ConfigError(f"duplicate source url: {url}")
            seen_urls.add(key)
        try:
            render_mode = RenderMode(s.get("render_mode", RenderMode.HTTP.value))
        except ValueError as exc:
            raise ConfigError(f"bad render_mode: {s['id']}") from exc
        render_wait_selector = s.get("render_wait_selector")
        if render_wait_selector is not None and not isinstance(
            render_wait_selector, str
        ):
            raise ConfigError(f"bad render_wait_selector: {s['id']}")
        raw_fallback_source_ids = s.get("fallback_source_ids", [])
        if not isinstance(raw_fallback_source_ids, list) or not all(
            isinstance(value, str) and value
            for value in raw_fallback_source_ids
        ):
            raise ConfigError(f"bad fallback_source_ids: {s['id']}")
        activation_group = str(s.get("activation_group", ALWAYS_ON_GROUP))
        if activation_group not in _ALLOWED_ACTIVATION_GROUPS:
            raise ConfigError(
                f"bad activation_group: {s['id']}={activation_group}"
            )
        application_method = s.get("application_method")
        if application_method is not None and not isinstance(
            application_method, str
        ):
            raise ConfigError(f"bad application_method: {s['id']}")
        try:
            lottery_start_policy = LotteryStartPolicy(
                str(
                    s.get(
                        "lottery_start_policy",
                        LotteryStartPolicy.AUTO.value,
                    )
                )
            )
        except ValueError as exc:
            allowed = ", ".join(policy.value for policy in LotteryStartPolicy)
            raise ConfigError(
                f"bad lottery_start_policy: {s['id']}; allowed={allowed}"
            ) from exc
        required_store_visits = s.get("required_store_visits")
        if required_store_visits is not None and (
            isinstance(required_store_visits, bool)
            or not isinstance(required_store_visits, int)
            or required_store_visits < 0
        ):
            raise ConfigError(f"bad required_store_visits: {s['id']}")
        if activation_group == TOHOKU_EXPEDITION_GROUP and (
            application_method != "web" or required_store_visits != 1
        ):
            raise ConfigError(
                "tohoku_expedition source must be web application and require "
                f"exactly one store visit: {s['id']}"
            )
        sources.append(
            SourceConfig(
                id=s["id"],
                name=s["name"],
                source_tier=tier,
                supported_games=supported_games,
                purposes=_list(s.get("purposes")),
                enabled=bool(s.get("enabled", True)),
                discovery_urls=_list(s.get("discovery_urls")),
                start_labels=_list(s.get("start_labels")),
                render_mode=render_mode,
                render_wait_selector=render_wait_selector,
                poll_minutes=int(s.get("poll_minutes", 10)),
                selectors={k: _list(v) for k, v in (s.get("selectors") or {}).items()},
                expected_elements=_list(s.get("expected_elements")),
                robots_url=s.get("robots_url"),
                fallback_source_ids=list(raw_fallback_source_ids),
                activation_group=activation_group,
                application_method=application_method,
                required_store_visits=required_store_visits,
                lottery_start_policy=lottery_start_policy,
                fallback_on_empty_result=bool(
                    s.get("fallback_on_empty_result", False)
                ),
            )
        )
    _validate_fallback_sources(sources)
    return Config(
        raw["schema_version"],
        raw.get("timezone", "Asia/Tokyo"),
        system,
        games,
        dict(raw.get("common_terms", {})),
        sources,
    )


def validate_config(path: str | Path = "sites.yaml") -> Config:
    return load_config(path)
