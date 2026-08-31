from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tcg_monitor.config import ConfigError, load_config
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.pipeline import run_pipeline
from tcg_monitor.source_groups import (
    ALWAYS_ON_GROUP,
    EXPEDITION_GROUPS,
    EXPEDITION_SENDAI_GROUP,
    EXPEDITION_TOKYO_GROUP,
    EXPEDITION_TOKYO_ROUTE_GROUP,
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

SENDAI_SOURCES = {
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

TOKYO_ROUTE_SOURCES = {
    "yahoo_realtime_batoloco_fukushima": (
        "batoloco_fuku",
        "TCバトロコ福島駅前",
    ),
    "yahoo_realtime_hareruya2": (
        "hareruya2pokeca",
        "晴れる屋2",
    ),
    "yahoo_realtime_batoloco_oyama": (
        "batoloco_oyama",
        "TCバトロコ小山駅前",
    ),
    "yahoo_realtime_pao_omiya": (
        "PAOtoreka_omiya",
        "カードショップ竜星のPAO大宮店",
    ),
}

TOKYO_SOURCES = {
    "yahoo_realtime_cardwings_akihabara_pokemon": (
        "CARDWINGS_POKE",
        "CARD WINGS秋葉原駅前店",
    ),
    "yahoo_realtime_dragonstar_akihabara_ekimae": (
        "ds_akiba_ekimae",
        "ドラゴンスター秋葉原駅前店",
    ),
    "yahoo_realtime_bigmagic_akihabara": (
        "bigmagicakb",
        "BIG MAGIC秋葉原店",
    ),
    "yahoo_realtime_fukufuku_akihabara": (
        "fukufuku_toreka",
        "福福トレカ秋葉原店",
    ),
    "yahoo_realtime_fukufuku_akihabara_onepiece": (
        "fukufuku_one",
        "福福トレカ秋葉原店",
    ),
    "yahoo_realtime_dragonstar_akihabara": (
        "ds_akiba",
        "ドラゴンスター秋葉原店",
    ),
    "yahoo_realtime_mint_games_ikebukuro": (
        "MintGames_IKB",
        "MINT GAMES池袋店",
    ),
    "yahoo_realtime_batoloco_ikebukuro": (
        "Batoloco_1852",
        "TCバトロコ池袋駅前店",
    ),
    "yahoo_realtime_dragonstar_ikebukuro": (
        "ds_ikebukur0",
        "ドラゴンスター池袋店",
    ),
    "yahoo_realtime_bigmagic_ikebukuro_pokemon": (
        "BMike_pokemon",
        "BIG MAGIC池袋店",
    ),
    "yahoo_realtime_bigmagic_ikebukuro": (
        "BM_ikebukuro",
        "BIG MAGIC池袋店",
    ),
    "yahoo_realtime_batoloco_shibuya_satellite": (
        "batoloco_428",
        "TCバトロコsatellite渋谷駅前店",
    ),
    "yahoo_realtime_pokemon_card_lounge_shibuya": (
        "PCGL_Shibuya",
        "POKÉMON CARD LOUNGE",
    ),
    "yahoo_realtime_mint_shibuya": (
        "mint_shibuya",
        "MINT渋谷店",
    ),
    "yahoo_realtime_tierone_shibuya": (
        "TierOneshibuya",
        "TierOne渋谷店",
    ),
    "yahoo_realtime_batoloco_shibuya_center": (
        "batoloco_1825",
        "TCバトロコ渋谷センター街店",
    ),
    "yahoo_realtime_mint_shinjuku": (
        "mintshinjuku",
        "MINT新宿店",
    ),
}

GROUP_SOURCES = {
    EXPEDITION_SENDAI_GROUP: SENDAI_SOURCES,
    EXPEDITION_TOKYO_ROUTE_GROUP: TOKYO_ROUTE_SOURCES,
    EXPEDITION_TOKYO_GROUP: TOKYO_SOURCES,
}
ALL_EXPEDITION_SOURCES = {
    source_id
    for group_sources in GROUP_SOURCES.values()
    for source_id in group_sources
}


def test_exactly_the_reviewed_one_visit_sources_are_in_each_expedition_group() -> None:
    config = load_config("sites.yaml")

    for group, expected in GROUP_SOURCES.items():
        actual = {
            source.id: source
            for source in config.sources
            if source.activation_group == group
        }
        assert set(actual) == set(expected)
        assert all(source.application_method == "web" for source in actual.values())
        assert all(source.required_store_visits == 1 for source in actual.values())


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
            **SENDAI_SOURCES,
            **TOKYO_ROUTE_SOURCES,
            **TOKYO_SOURCES,
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
    expected_urls = [
        (
            "https://search.yahoo.co.jp/realtime/search?"
            f"p=id%3A{account}%20%E6%8A%BD%E9%81%B8&ei=UTF-8"
        ),
        f"https://twstalker.com/{account}",
    ]
    if source.activation_group in {
        EXPEDITION_TOKYO_ROUTE_GROUP,
        EXPEDITION_TOKYO_GROUP,
    }:
        expected_urls.append(
            "https://www.bing.com/search?format=rss&"
            f"q=site%3Ax.com%2F{account}%2Fstatus+%E6%8A%BD%E9%81%B8&"
            "setlang=ja-JP&cc=jp"
        )
    assert source.discovery_urls == expected_urls

    product = (
        "ポケカ 拡張パック『遠征監視テスト』1BOX"
        if source.supports("pokemon_card")
        else "ONE PIECEカードゲーム ブースターパック『遠征監視テスト』1BOX"
    )
    html = f"""
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      {retailer_name} {product} 抽選販売のお知らせ
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
    assert cases[0].source_url == f"https://x.com/{account}/status/2079755316506599865"


def test_bing_rss_fallback_parses_an_official_x_post() -> None:
    config = load_config("sites.yaml")
    source = next(
        item
        for item in config.sources
        if item.id == "yahoo_realtime_batoloco_fukushima"
    )
    rss = """<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>TCバトロコ福島駅前 抽選販売のお知らせ</title>
          <link>https://x.com/batoloco_fuku/status/2079755316506599865</link>
          <description>
            ポケカ 拡張パック『遠征監視テスト』1BOX
            応募受付期間：7/24(金) 10:00から
          </description>
        </item>
      </channel>
    </rss>
    """

    cases, _, alerts = parse_yahoo_realtime(
        rss,
        source.discovery_urls[-1],
        source,
        config,
        date(2026, 7, 24),
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_name == "TCバトロコ福島駅前"
    assert cases[0].source_url == (
        "https://x.com/batoloco_fuku/status/2079755316506599865"
    )


def test_tierone_still_open_round_uses_verified_deadline_and_product() -> None:
    config = load_config("sites.yaml")
    source = next(
        item for item in config.sources if item.id == "yahoo_realtime_tierone_shibuya"
    )
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      【ポケモンカード 販売情報】
      ポケモンカード1BOXの抽選受付を開始しました。
      応募受付期間：8/16(日) 00:00から
      </p>
      <time><a href="https://x.com/TierOneshibuya/status/2088908861440930266">
      8月16日
      </a></time>
    </div>
    """

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        config,
        date(2026, 8, 31),
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].product_name == "拡張パック「30th CELEBRATION」"
    assert cases[0].end_at == datetime(
        2026,
        9,
        13,
        23,
        59,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )


@pytest.mark.parametrize(
    ("source_id", "account", "application_text"),
    [
        (
            "yahoo_realtime_batoloco_ikebukuro",
            "Batoloco_1852",
            "応募方法は当アカウントをフォロー＆リポスト",
        ),
        (
            "yahoo_realtime_bigmagic_akihabara",
            "bigmagicakb",
            "店頭に掲示されたQRコードより応募してください",
        ),
        (
            "yahoo_realtime_dragonstar_ikebukuro",
            "ds_ikebukur0",
            "当選された方は店頭にて予約を行う必要があります。予約手付金が必要です",
        ),
    ],
)
def test_repost_store_qr_and_two_visit_rounds_are_rejected(
    source_id: str,
    account: str,
    application_text: str,
) -> None:
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == source_id)
    html = f"""
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      ポケカ 拡張パック『遠征除外テスト』1BOX 抽選販売
      応募受付期間：7/24(金) 10:00から
      {application_text}
      </p>
      <time><a href="https://x.com/{account}/status/2079755316506599865">
      7月24日
      </a></time>
    </div>
    """

    cases, releases, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        config,
        date(2026, 7, 24),
    )

    assert cases == []
    assert releases == []
    assert alerts == []


def test_shibuya_satellite_feed_does_not_claim_center_store_posts() -> None:
    config = load_config("sites.yaml")
    source = next(
        item
        for item in config.sources
        if item.id == "yahoo_realtime_batoloco_shibuya_satellite"
    )
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      こちらは渋谷センター街店の抽選フォームです。
      ポケカ 拡張パック『店舗判別テスト』1BOX 抽選販売
      応募受付期間：7/24(金) 10:00から
      </p>
      <time><a href="https://x.com/batoloco_428/status/2079755316506599865">
      7月24日
      </a></time>
    </div>
    """

    cases, releases, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        config,
        date(2026, 7, 24),
    )

    assert cases == []
    assert releases == []
    assert alerts == []


class _NoNetworkFetcher:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, *_args: object, **_kwargs: object) -> object:
        self.calls += 1
        raise AssertionError("OFF中の遠征監視がネットワークへ到達しました")


def test_off_modes_stop_expedition_sources_before_network_access() -> None:
    config = load_config("sites.yaml")
    source_filter = active_source_filter(
        config.sources,
        set(ALL_EXPEDITION_SOURCES),
        enabled_expedition_groups=frozenset(),
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


@pytest.mark.parametrize("enabled_group", sorted(EXPEDITION_GROUPS))
def test_each_mode_adds_only_its_group(enabled_group: str) -> None:
    config = load_config("sites.yaml")
    normal_sources = {
        source.id
        for source in config.sources
        if source.enabled and source.activation_group == ALWAYS_ON_GROUP
    }

    source_filter = active_source_filter(
        config.sources,
        None,
        enabled_expedition_groups={enabled_group},
    )

    assert source_filter == normal_sources | set(GROUP_SOURCES[enabled_group])


def test_all_modes_add_all_expedition_sources() -> None:
    config = load_config("sites.yaml")
    normal_sources = {
        source.id
        for source in config.sources
        if source.enabled and source.activation_group == ALWAYS_ON_GROUP
    }

    off_filter = active_source_filter(
        config.sources,
        None,
        enabled_expedition_groups=frozenset(),
    )
    on_filter = active_source_filter(
        config.sources,
        None,
        enabled_expedition_groups=EXPEDITION_GROUPS,
    )

    assert off_filter == normal_sources
    assert on_filter == normal_sources | ALL_EXPEDITION_SOURCES


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("application_method: web", "application_method: in_store"),
        ("required_store_visits: 1", "required_store_visits: 2"),
    ],
)
def test_config_rejects_expedition_sources_that_are_not_web_and_one_visit(
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
