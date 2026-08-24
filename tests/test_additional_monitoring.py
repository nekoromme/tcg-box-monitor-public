from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tcg_monitor.config import ConfigError, load_config
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.pipeline import run_pipeline
from tcg_monitor.source_groups import (
    ADDITIONAL_GROUP,
    ALWAYS_ON_GROUP,
    active_source_filter,
)

PROMOTED_ALWAYS_ON_SOURCES = {
    "yahoo_realtime_batoloco_sendai": (
        "batoloco_SND",
        "TCバトロコ仙台駅東口",
    ),
    "yahoo_realtime_tcgpit_sendai": (
        "tcgpit_sendai",
        "トレーディングカードピット仙台駅東口店",
    ),
}

ADDITIONAL_SOURCES = {
    "yahoo_realtime_santy_sendai": (
        "santycrissroad",
        "santy仙台クリスロード店",
    ),
    "yahoo_realtime_tsutaya_higashi_sendai": (
        "YTHtoreka",
        "TSUTAYAヤマト屋書店東仙台店",
    ),
    "yahoo_realtime_tsutaya_chomeigaoka": (
        "TBSSENDAICHOMEI",
        "TSUTAYA BOOKSTORE仙台長命ヶ丘",
    ),
    "yahoo_realtime_surugaya_rifu": (
        "SURUGAYA_RIFU",
        "駿河屋イオンモール新利府南館店",
    ),
    "yahoo_realtime_omocha_no_ousama": (
        "KingOfToyss",
        "おもちゃの王様",
    ),
}


def test_exactly_the_reviewed_one_visit_sources_are_in_additional_group() -> None:
    config = load_config("sites.yaml")
    additional_sources = {
        source.id: source
        for source in config.sources
        if source.activation_group == ADDITIONAL_GROUP
    }

    assert set(additional_sources) == set(ADDITIONAL_SOURCES)
    assert all(source.application_method == "web" for source in additional_sources.values())
    assert all(source.required_store_visits == 1 for source in additional_sources.values())


@pytest.mark.parametrize(
    "source_id",
    [
        "yahoo_realtime_batoloco_morioka",
        *PROMOTED_ALWAYS_ON_SOURCES,
    ],
)
def test_promoted_sources_are_always_on(source_id: str) -> None:
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == source_id)

    assert source.activation_group == ALWAYS_ON_GROUP
    assert source.enabled is True


@pytest.mark.parametrize(
    ("source_id", "account", "retailer_name"),
    [
        (source_id, account, retailer_name)
        for source_id, (account, retailer_name) in {
            **PROMOTED_ALWAYS_ON_SOURCES,
            **ADDITIONAL_SOURCES,
        }.items()
    ],
)
def test_reviewed_sources_parse_their_official_x_posts(
    source_id: str,
    account: str,
    retailer_name: str,
) -> None:
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == source_id)
    assert source.discovery_urls == [
        (
            "https://search.yahoo.co.jp/realtime/search?"
            f"p=id%3A{account}%20%E6%8A%BD%E9%81%B8&ei=UTF-8"
        ),
        f"https://twstalker.com/{account}",
    ]

    html = f"""
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      ポケカ 拡張パック「追加監視テスト」1BOX 抽選販売のお知らせ
      応募受付期間：7/24(金) 10:00から
      </p>
      <time><a href="https://x.com/{account}/status/2079755316506599865">
      7月24日
      </a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        config,
        date(2026, 7, 24),
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_name == retailer_name
    assert cases[0].source_url == (f"https://x.com/{account}/status/2079755316506599865")


class _NoNetworkFetcher:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, *_args: object, **_kwargs: object) -> object:
        self.calls += 1
        raise AssertionError("OFF中の追加監視がネットワークへ到達しました")


def test_off_mode_stops_additional_sources_before_network_access() -> None:
    config = load_config("sites.yaml")
    source_filter = active_source_filter(
        config.sources,
        set(ADDITIONAL_SOURCES),
        additional_monitoring_enabled=False,
    )
    assert source_filter == set()

    fetcher = _NoNetworkFetcher()
    cases, releases, alerts = run_pipeline(
        config,
        source_filter=source_filter,
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert fetcher.calls == 0
    assert cases == []
    assert releases == []
    assert alerts == []


def test_on_mode_adds_additional_sources_without_changing_normal_sources() -> None:
    config = load_config("sites.yaml")
    normal_sources = {
        source.id
        for source in config.sources
        if source.enabled and source.activation_group == ALWAYS_ON_GROUP
    }

    off_filter = active_source_filter(
        config.sources,
        None,
        additional_monitoring_enabled=False,
    )
    on_filter = active_source_filter(
        config.sources,
        None,
        additional_monitoring_enabled=True,
    )

    assert off_filter == normal_sources
    assert on_filter == normal_sources | set(ADDITIONAL_SOURCES)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("application_method: web", "application_method: in_store"),
        ("required_store_visits: 1", "required_store_visits: 2"),
    ],
)
def test_config_rejects_additional_sources_that_are_not_web_and_one_visit(
    tmp_path: Path,
    old: str,
    new: str,
) -> None:
    original = Path("sites.yaml").read_text(encoding="utf-8")
    marker = "- id: yahoo_realtime_santy_sendai"
    start = original.index(marker)
    end = original.find("\n- id:", start + len(marker))
    block = original[start:] if end == -1 else original[start:end]
    assert old in block
    invalid_block = block.replace(old, new, 1)
    invalid = (
        original[:start] + invalid_block
        if end == -1
        else original[:start] + invalid_block + original[end:]
    )
    path = tmp_path / "invalid-sites.yaml"
    path.write_text(invalid, encoding="utf-8")

    with pytest.raises(
        ConfigError,
        match="must use web application and require exactly one store visit",
    ):
        load_config(path)
