from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tcg_monitor.config import ConfigError, load_config
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.parsers.retailer_lottery import discover_retailer_lottery_urls
from tcg_monitor.source_groups import (
    EXPEDITION_SENDAI_GROUP,
    active_source_filter,
)


def _overlay(tmp_path: Path, source_body: str) -> Path:
    path = tmp_path / "runtime-overlay.yaml"
    path.write_text(
        "schema_version: 1\n"
        "source_overrides: {}\n"
        "sources:\n"
        f"{source_body}",
        encoding="utf-8",
    )
    return path


def test_runtime_overlay_can_add_a_generic_source(
    tmp_path: Path,
) -> None:
    overlay = _overlay(
        tmp_path,
        """- id: example_store_feed
  name: 追加監視先A
  source_tier: official_indirect
  coverage_scope: specialized
  supported_games:
    pokemon_card: verified
  purposes: [lottery_discovery]
  enabled: true
  poll_minutes: 120
  discovery_urls:
    - https://example.invalid/private-store
  activation_group: expedition_sendai
  application_method: web
  required_store_visits: 1
  parser_kind: yahoo_realtime
  parser_options:
    account: example_store
    retailer_id: example_store
    retailer_name: 追加監視先A
""",
    )

    config = load_config("sites.yaml", private_config_path=overlay)
    source = next(item for item in config.sources if item.id == "example_store_feed")

    assert source.activation_group == EXPEDITION_SENDAI_GROUP
    assert source.parser_options["account"] == "example_store"
    assert source.poll_minutes == config.system["uniform_source_poll_minutes"]

    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      ポケカ 拡張パック「ストームエメラルダ」1BOX 抽選販売のお知らせ
      応募受付期間：8/22(土) 10:00から
      </p>
      <time><a href="https://x.com/example_store/status/2079755316506599865">
      8月22日
      </a></time>
    </div>
    """
    cases, releases, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        config,
        date(2026, 8, 22),
    )

    assert not releases
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "example_store"


@pytest.mark.parametrize(
    ("field", "value"),
    [("application_method", "in_store"), ("required_store_visits", "2")],
)
def test_additional_source_must_be_web_and_one_visit(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    overlay = _overlay(
        tmp_path,
        f"""- id: example_store_feed
  name: 追加監視先A
  source_tier: official
  coverage_scope: specialized
  supported_games:
    pokemon_card: verified
  purposes: [lottery_discovery]
  enabled: true
  poll_minutes: 120
  discovery_urls: [https://example.invalid/private-store]
  activation_group: expedition_sendai
  application_method: {value if field == 'application_method' else 'web'}
  required_store_visits: {value if field == 'required_store_visits' else '1'}
""",
    )

    with pytest.raises(ConfigError, match="must use web application"):
        load_config("sites.yaml", private_config_path=overlay)


def test_generic_retailer_profile_limits_detail_links(tmp_path: Path) -> None:
    overlay = _overlay(
        tmp_path,
        """- id: example_retailer_index
  name: 追加購入権ページ
  source_tier: official
  coverage_scope: specialized
  supported_games:
    one_piece_card: verified
  purposes: [lottery_discovery]
  enabled: true
  poll_minutes: 120
  discovery_urls: [https://tickets.example.invalid/list/]
  parser_kind: retailer_lottery
  parser_options:
    index_url: https://tickets.example.invalid/list/
    detail_host: tickets.example.invalid
    detail_path_prefix: /entry/
    detail_path_suffix: .html
    target_context_markers: [対象店舗]
    required_context_markers: [抽選, 購入権]
    retailers:
      - marker: 対象店舗
        retailer_id: example_retailer
        retailer_name: 追加監視先B
""",
    )
    config = load_config("sites.yaml", private_config_path=overlay)
    source = next(
        item for item in config.sources if item.id == "example_retailer_index"
    )
    html = """
    <ul>
      <li><a href="/entry/target.html">対象店舗 抽選 購入権
      ONE PIECEカードゲーム ブースターパック 1BOX</a></li>
      <li><a href="/entry/other.html">別店舗 抽選 購入権
      ONE PIECEカードゲーム ブースターパック 1BOX</a></li>
    </ul>
    """

    assert discover_retailer_lottery_urls(
        html,
        source.discovery_urls[0],
        source,
        config,
    ) == ["https://tickets.example.invalid/entry/target.html"]


def test_additional_sources_default_to_disabled_without_runtime() -> None:
    config = load_config("sites.yaml", private_config_path="")
    assert active_source_filter(
        config.sources,
        set(),
        enabled_expedition_groups=frozenset(),
    ) == set()


def test_parser_options_must_be_a_mapping(tmp_path: Path) -> None:
    overlay = _overlay(
        tmp_path,
        """- id: example_store_feed
  name: 追加監視先A
  source_tier: official
  coverage_scope: specialized
  supported_games:
    pokemon_card: verified
  purposes: [lottery_discovery]
  enabled: true
  poll_minutes: 120
  discovery_urls: [https://example.invalid/private-store]
  parser_kind: yahoo_realtime
  parser_options: invalid
""",
    )

    with pytest.raises(ConfigError, match="bad parser_options"):
        load_config("sites.yaml", private_config_path=overlay)
