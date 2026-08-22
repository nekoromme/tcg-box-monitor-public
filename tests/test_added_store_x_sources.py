from __future__ import annotations

from datetime import date

import pytest

from tcg_monitor.config import load_config
from tcg_monitor.models import OpportunityKind
from tcg_monitor.parsers.local_lottery import (
    parse_meli_melo_douraku_current,
    parse_yahoo_realtime,
    yahoo_repair_discovery_urls,
)


@pytest.mark.parametrize(
    ("source_id", "account", "retailer_name"),
    [
        ("yahoo_realtime_pokedou_morioka", "PokedouTencho_M", "ポケ堂盛岡店"),
        ("yahoo_realtime_pokedou_kitakami", "PokedouTencho_K", "ポケ堂北上店"),
        ("yahoo_realtime_tsutaya_tsukidate", "tsukidateten", "TSUTAYA築館店"),
    ],
)
def test_added_store_x_sources_are_wired_to_the_official_accounts(
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
      ポケカ 拡張パック「監視テスト」1BOX 抽選販売のお知らせ
      受付期間：7/24(金) 10:00から
      </p>
      <time><a href="https://x.com/{account}/status/2079755316506599865">7月24日</a></time>
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
    assert cases[0].source_url == (
        f"https://x.com/{account}/status/2079755316506599865"
    )


def test_priority_sendai_sources_fall_back_when_yahoo_is_empty() -> None:
    by_id = {source.id: source for source in load_config("sites.yaml").sources}

    for source_id in (
        "yahoo_realtime_torecaplaza55",
        "yahoo_realtime_toreca_douraku_sendai",
        "yahoo_realtime_magi_sendai",
        "yahoo_realtime_hmv",
    ):
        assert by_id[source_id].enabled
        assert by_id[source_id].fallback_on_empty_result
        assert by_id[source_id].poll_minutes == 120

    magi = by_id["yahoo_realtime_magi_sendai"]
    assert magi.discovery_urls == [
        (
            "https://search.yahoo.co.jp/realtime/search?"
            "p=id%3Amagi_sendai%20%E6%8A%BD%E9%81%B8&ei=UTF-8"
        ),
        "https://twstalker.com/magi_sendai",
    ]
    assert magi.lottery_start_policy.value == "first_detection"
    douraku = by_id["yahoo_realtime_toreca_douraku_sendai"]
    assert douraku.lottery_start_policy.value == "first_detection"
    assert "p=%E3%83%88%E3%83%AC%E3%82%AB%E9%81%93%E6%A5%BD" in (
        douraku.discovery_urls[2]
    )
    assert "/search/tweet/2084826013847130224" in douraku.discovery_urls[3]
    assert by_id["livepocket_hmv"].enabled
    hmv_secondary = by_id["yahoo_realtime_hmv_secondary"]
    assert hmv_secondary.enabled
    assert hmv_secondary.source_tier.value == "secondary"
    assert hmv_secondary.fallback_on_empty_result
    assert hmv_secondary.discovery_urls[1] == (
        "https://search.yahoo.co.jp/realtime/search?p=id%3Agamegetnavi&ei=UTF-8"
    )
    plaza_secondary = by_id["yahoo_realtime_torecaplaza55_secondary"]
    assert plaza_secondary.enabled
    assert plaza_secondary.source_tier.value == "secondary"
    assert plaza_secondary.lottery_start_policy.value == "first_detection"
    assert "/search/tweet/2088582782822055952" in (
        plaza_secondary.discovery_urls[2]
    )


def test_douraku_current_roundup_is_scoped_to_sendai_store() -> None:
    config = load_config("sites.yaml")
    source = next(
        item
        for item in config.sources
        if item.id == "meli_melo_toreca_douraku_current"
    )
    html = """
    <html><head><title>ワンピカード 世界最強の戦士 抽選販売開始</title></head>
    <body>
      <p>2026年8月22日発売 ブースターパック 世界最強の戦士【OP-17】</p>
      <h2>別の店舗</h2><p>応募期間：2026年8月15日～8月16日</p>
      <h2>トレカ道楽　郵送・店頭受け取りどちらも可</h2>
      <p>仙台駅前アーケード店：
        <a href="https://x.com/Dourakusendai/status/2084826013847130224">
          応募・詳細
        </a>
      </p>
      <p>応募期間：2026年8月3日(月)～8月22日(土)</p>
      <h2>コーギーアール</h2>
    </body></html>
    """

    cases, releases, alerts = parse_meli_melo_douraku_current(
        html,
        source.discovery_urls[0],
        source,
        config,
    )

    assert not releases
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "toreca_douraku_sendai"
    assert cases[0].canonical_product_key == "OP-17"
    assert cases[0].start_at == date(2026, 8, 3)
    assert cases[0].end_at == date(2026, 8, 22)
    assert cases[0].official_url == (
        "https://x.com/Dourakusendai/status/2084826013847130224"
    )
    assert cases[0].source_tier.value == "secondary"


def test_plaza55_secondary_recovers_deadline_only_current_lottery() -> None:
    config = load_config("sites.yaml")
    source = next(
        item
        for item in config.sources
        if item.id == "yahoo_realtime_torecaplaza55_secondary"
    )
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      【ポケモンカード抽選販売（再販）】
      トレカプラザ55通販店で拡張パック「ストームエメラルダ」1BOXの
      抽選販売受付開始。応募締切：8月25日(火)23:59まで
      </p>
      <a href="https://docs.google.com/forms/d/e/example/viewform">応募ページ</a>
      <time><a href="https://x.com/pokecamatomeru/status/2088582782822055952">
        8月15日
      </a></time>
    </div>
    """

    cases, releases, alerts = parse_yahoo_realtime(
        html,
        source.discovery_urls[0],
        source,
        config,
        date(2026, 8, 16),
    )

    assert not releases
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "torecaplaza55"
    assert cases[0].product_name == "拡張パック「ストームエメラルダ」"
    assert cases[0].start_at == date(2026, 8, 16)
    assert cases[0].source_tier.value == "secondary"
    assert cases[0].extraction_method == "yahoo_realtime_detected_open"


@pytest.mark.parametrize(
    ("source_id", "account", "retailer_name"),
    [
        ("yahoo_realtime_geo_official", "GEO_official", "ゲオ"),
        ("yahoo_realtime_yodobashi", "Yodobashi_X", "ヨドバシカメラ"),
        (
            "yahoo_realtime_pokemon_center_store",
            "pokemoncenterPR",
            "ポケモンセンター（店頭）",
        ),
    ],
)
def test_access_limited_retailers_have_official_x_fallbacks(
    source_id: str,
    account: str,
    retailer_name: str,
) -> None:
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == source_id)
    assert len(source.discovery_urls) == 1
    assert f"id%3A{account}" in source.discovery_urls[0]

    html = f"""
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      ポケモンカードゲーム 拡張パック「監視テスト」1BOX
      抽選販売のお知らせ
      応募受付期間：7月24日（金）10時から
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
    assert cases[0].source_url == (
        f"https://x.com/{account}/status/2079755316506599865"
    )


@pytest.mark.parametrize(
    ("source_id", "account", "retailer_name"),
    [
        ("yahoo_realtime_konami_style", "konamistyle", "KONAMI STYLE"),
        (
            "yahoo_realtime_kids_republic_official",
            "kidsrepublicjp",
            "キッズリパブリック",
        ),
    ],
)
def test_added_official_x_fallbacks_parse_yugioh_box_lotteries(
    source_id: str,
    account: str,
    retailer_name: str,
) -> None:
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == source_id)
    assert source.discovery_urls == [
        source.discovery_urls[0],
        f"https://twstalker.com/{account}",
    ]
    assert f"id%3A{account}" in source.discovery_urls[0]

    html = f"""
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      遊戯王OCG ORIGINAL ARTWORK COLLECTION 1BOX
      抽選販売のお知らせ
      応募受付期間：7月24日（金）10時から
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
    assert cases[0].game_id == "yu_gi_oh"
    assert cases[0].retailer_name == retailer_name


def test_lorcana_official_x_fallback_parses_booster_reservation() -> None:
    config = load_config("sites.yaml")
    source = next(
        item
        for item in config.sources
        if item.id == "yahoo_realtime_lorcana_official"
    )
    assert source.discovery_urls == [
        (
            "https://search.yahoo.co.jp/realtime/search?"
            "p=id%3ADisneyLOR_JP%20%E7%99%BA%E5%A3%B2%20"
            "%E4%BA%88%E7%B4%84%E9%96%8B%E5%A7%8B&ei=UTF-8"
        ),
        "https://twstalker.com/DisneyLOR_JP",
    ]
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      【お知らせ】2026年8月28日発売予定
      ディズニー・ロルカナ・TCG 日本語版
      ブースターパック「監視テスト」1BOX
      まもなく予約開始
      </p>
      <time><a href="https://x.com/DisneyLOR_JP/status/2079755316506599865">
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
    assert cases[0].game_id == "lorcana"
    assert cases[0].retailer_name == "ディズニーロルカナ公式"
    assert cases[0].opportunity_kind == OpportunityKind.DIRECT_SALE_SEEN
    assert cases[0].extraction_method == "yahoo_realtime_official_sale_seen"


def test_geo_official_x_ignores_application_label_as_product_name() -> None:
    config = load_config("sites.yaml")
    source = next(
        item for item in config.sources if item.id == "yahoo_realtime_geo_official"
    )
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      2026/8/22(土)販売分 #ポケモンカードゲーム
      スカーレット&amp;バイオレット 拡張パック ホワイトフレアの
      <em>抽選</em> 販売をゲオアプリにて実施いたします。
      【抽選 受付期間】8/3(月) 11:00から8/6(木) 17:59まで
      【当選者への連絡日】8/20(木)
      【当選者へのお渡し期間】8/22(土)から8/23(日)
      </p>
      <time><a href="https://x.com/GEO_official/status/2080582562012119398">
      7月25日
      </a></time>
    </div>
    """

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        config,
        date(2026, 7, 25),
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].product_name == "拡張パック「ホワイトフレア」"
    assert str(cases[0].start_at) == "2026-08-03 11:00:00+09:00"


def test_geo_official_x_uses_ocr_product_and_application_range() -> None:
    config = load_config("sites.yaml")
    source = next(
        item for item in config.sources if item.id == "yahoo_realtime_geo_official"
    )
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      2026/7/31(金)発売 #ポケモンカードゲーム
      新作4商品の抽選販売をゲオアプリにて実施いたします。
      【対象商品】
      </p>
      <img src="https://pbs.twimg.com/media/geo-lottery.jpg">
      <time><a href="https://x.com/GEO_official/status/2072968946731594147">
      7月13日
      </a></time>
    </div>
    """
    ocr_text = """
    ポケモンカードゲーム MEGA 拡張パック ストームエメラルダ
    ポケモンカードゲーム MEGA スターターセットex
    抽選販売のお知らせ
    7/13(月) 11:00から7/16(木) 17:59まで
    """

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        config,
        date(2026, 7, 25),
        lambda _urls: ocr_text,
        {},
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].product_name == "拡張パック「ストームエメラルダ」"
    assert str(cases[0].start_at) == "2026-07-13 11:00:00+09:00"
    assert cases[0].extraction_method == "yahoo_realtime_image_ocr_application_period"


def test_yahoo_repair_urls_only_revisit_provisional_product_names() -> None:
    generic_status = "2080582562012119398"
    target_status = "2072968946731594147"
    seen_cases = {
        "generic-heading": {
            "retailer_id": "geo",
            "product_name": "拡張パック「当選者への連絡日」",
            "source_url": f"https://x.com/GEO_official/status/{generic_status}",
        },
        "generic-target": {
            "retailer_id": "geo",
            "product_name": "拡張パック「対象商品」",
            "source_url": f"https://x.com/GEO_official/status/{target_status}",
        },
        "already-correct": {
            "retailer_id": "geo",
            "product_name": "拡張パック「ストームエメラルダ」",
            "source_url": "https://x.com/GEO_official/status/2070000000000000000",
        },
        "different-retailer": {
            "retailer_id": "yodobashi",
            "product_name": "拡張パック「対象商品」",
            "source_url": "https://x.com/Yodobashi_X/status/2090000000000000000",
        },
    }

    assert yahoo_repair_discovery_urls(
        "yahoo_realtime_geo_official", seen_cases
    ) == [
        (
            "https://search.yahoo.co.jp/realtime/search/tweet/"
            f"{generic_status}?detail=1&ifr=tl_twdtl&rkf=1"
        ),
        (
            "https://search.yahoo.co.jp/realtime/search/tweet/"
            f"{target_status}?detail=1&ifr=tl_twdtl&rkf=1"
        ),
    ]
