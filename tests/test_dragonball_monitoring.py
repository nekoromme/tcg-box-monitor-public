from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from tcg_monitor.classifier import classify_product
from tcg_monitor.config import load_config
from tcg_monitor.parsers.dragonball_official import (
    discover_dragonball_official_store_urls,
    parse_dragonball_official_products,
    parse_dragonball_official_store_lottery,
)
from tcg_monitor.parsers.local_lottery import (
    parse_livepocket_event,
    parse_yahoo_realtime,
)


def _source(source_id: str):  # type: ignore[no-untyped-def]
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == source_id)
    return config, source


def test_dragonball_calendar_prefixes_are_short() -> None:
    config = load_config("sites.yaml")
    game = config.games["dragon_ball_fusion_world"]

    assert game.release_notification_prefix == "【ドラゴ発売】"
    assert game.release_calendar_prefix == "【ドラゴ発売】"
    assert game.lottery_schedule_prefix == "【ドラゴ抽選】"
    assert game.lottery_start_prefix == "【ドラゴ抽選】"


def test_dragonball_source_coverage_includes_general_retailers_only() -> None:
    config = load_config("sites.yaml")
    by_id = {source.id: source for source in config.sources}

    expected = {
        "dragonball_official_products",
        "dragonball_official_store",
        "yahoo_realtime_dragonball_official_store",
        "geo",
        "rakuten_books",
        "yodobashi",
        "kids_republic",
        "aeon_style_online",
        "yamada_denki",
        "kojima",
        "amazon_jp",
        "livepocket_hobby_station",
        "livepocket_tsutaya_akebono",
        "livepocket_fullcomp",
        "yahoo_realtime_tsutaya_tsukidate",
        "yahoo_realtime_furuichi",
        "yahoo_realtime_hmv",
    }
    assert all(
        "dragon_ball_fusion_world" in by_id[source_id].supported_games for source_id in expected
    )

    # These stores/sites have a title-specific scope and must not generate Dragon Ball noise.
    excluded = {
        "pokemon_center_online",
        "pokemon_center_store",
        "onepiece_official_products",
        "onepiece_official_topics",
        "yahoo_realtime_hareruya2",
        "yahoo_realtime_pokedou_morioka",
        "yahoo_realtime_pokedou_kitakami",
    }
    assert all(
        "dragon_ball_fusion_world" not in by_id[source_id].supported_games for source_id in excluded
    )


def test_dragonball_official_catalog_parses_boosters_and_excludes_starter_decks() -> None:
    config, source = _source("dragonball_official_products")
    html = """
    <nav>
      <a href="/fw/jp/products/01_401.html">STORY BOOSTER 01 [ST01]</a>
    </nav>
    <main>
      <a href="/fw/jp/products/01_401.html">
        STORY BOOSTER 01 [ST01] 発売日 2026.08.08
      </a>
      <a href="/fw/jp/products/01_422.html">
        ブースターパック BRIGHTNESS OF HOPE [FB11] 発売日 2026.09.12
      </a>
      <a href="/fw/jp/products/01_477.html">
        ブースターパック REACH THE GOD [FB12] 発売日 2026.12.12
      </a>
      <a href="/fw/jp/products/01_478.html">
        スタートデッキ サイヤ人の王子 [FS14] 発売日 2026.12.12
      </a>
    </main>
    """

    _, releases, alerts = parse_dragonball_official_products(
        html,
        "https://www.dbs-cardgame.com/fw/jp/products/",
        source,
        config,
    )

    by_key = {release.canonical_product_key: release for release in releases}
    assert set(by_key) == {"ST01", "FB11", "FB12"}
    assert by_key["ST01"].release_date == date(2026, 8, 8)
    assert by_key["FB11"].release_date == date(2026, 9, 12)
    assert by_key["FB12"].release_date == date(2026, 12, 12)
    assert not alerts


def test_dragonball_official_store_waits_for_real_application_start() -> None:
    config, source = _source("dragonball_official_store")
    index = """
    <a href="/official_shop/dbs-cardgame/news/important/20260714.html">
      8/8（土）発売のブースターパック販売方法について
    </a>
    """
    article_url = (
        "https://bandainamco-am.co.jp/official_shop/dbs-cardgame/news/important/20260714.html"
    )
    assert discover_dragonball_official_store_urls(
        index,
        "https://bandainamco-am.co.jp/official_shop/dbs-cardgame/",
    ) == [article_url]

    pending_html = """
    <h1>8/8発売のブースターパック販売方法について</h1>
    <main>
      ドラゴンボールスーパーカードゲーム フュージョンワールド
      STORY BOOSTER 01 [ST01] 1BOX
      事前抽選での販売を予定しております。
      詳細は準備が整い次第ご案内します。
    </main>
    """
    pending_cases, _, pending_alerts = parse_dragonball_official_store_lottery(
        pending_html,
        article_url,
        source,
        config,
    )
    assert not pending_cases
    assert not pending_alerts

    open_html = """
    <h1>STORY BOOSTER 01 [ST01] 事前抽選販売</h1>
    <main>
      ドラゴンボールスーパーカードゲーム フュージョンワールド
      対象商品 STORY BOOSTER 01 [ST01] 1BOX
      事前抽選応募期間：2026年7月25日(土) 10:00 ～ 7月28日(火) 23:59
    </main>
    """
    cases, _, alerts = parse_dragonball_official_store_lottery(
        open_html,
        article_url,
        source,
        config,
    )
    assert len(cases) == 1
    assert cases[0].retailer_id == "dragonball_official_store"
    assert cases[0].canonical_product_key == "ST01"
    assert cases[0].start_at == datetime(
        2026,
        7,
        25,
        10,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )
    assert not alerts


def test_dragonball_official_store_parses_actual_application_period_label() -> None:
    config, source = _source("dragonball_official_store")
    html = """
    <h1>『ブースターパック STORY BOOSTER 01 [ST01]』事前抽選について</h1>
    <main>
      <h3>『ブースターパック STORY BOOSTER 01 [ST01]』事前抽選について</h3>
      <p>「事前抽選」でのご案内となります。</p>
      <table>
        <tr><th>抽選販売日</th><td>2026年8月8日(土)・9日(日)販売分</td></tr>
        <tr>
          <th>実施内容</th>
          <td>『ブースターパック STORY BOOSTER 01 [ST01]』を抽選で販売</td>
        </tr>
        <tr>
          <th>申込受付期間</th>
          <td>2026年7月29日(水) 10:00 ～ 8月2日(日) 23:59</td>
        </tr>
      </table>
    </main>
    """
    url = "https://bandainamco-am.co.jp/official_shop/dbs-cardgame/news/important/20260728.html"

    cases, _, alerts = parse_dragonball_official_store_lottery(
        html,
        url,
        source,
        config,
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].canonical_product_key == "ST01"
    assert cases[0].start_at == datetime(
        2026,
        7,
        29,
        10,
        0,
        tzinfo=ZoneInfo("Asia/Tokyo"),
    )


def test_dragonball_livepocket_and_official_x_are_recognized() -> None:
    config, livepocket = _source("livepocket_hobby_station")
    livepocket_html = """
    <h1>フュージョンワールド STORY BOOSTER 01 [ST01] BOX購入権抽選</h1>
    <main>
      ドラゴンボールスーパーカードゲーム フュージョンワールド
      STORY BOOSTER 01 [ST01] 1BOX
      販売受付期間：2026年7月25日 10:00 ～ 2026年7月28日 23:59
    </main>
    """
    cases, _, alerts = parse_livepocket_event(
        livepocket_html,
        "https://livepocket.jp/e/dragonball-test",
        livepocket,
        config,
    )
    assert len(cases) == 1
    assert cases[0].game_id == "dragon_ball_fusion_world"
    assert cases[0].canonical_product_key == "ST01"
    assert not alerts

    _, official_x = _source("yahoo_realtime_dragonball_official_store")
    status_id = "2079755316506599865"
    x_html = f"""
    <div class="Tweet_TweetContainer">
      <a href="https://x.com/dbfw_cardgameJP/status/{status_id}">投稿</a>
      <p class="Tweet_body">
        ドラゴンボールスーパーカードゲーム フュージョンワールド
        STORY BOOSTER 01 [ST01] 1BOX 抽選販売
        応募期間 7/25(土) 10:00 ～ 7/28(火) 23:59
      </p>
      <time>2026-07-24</time>
    </div>
    """
    x_cases, _, x_alerts = parse_yahoo_realtime(
        x_html,
        "https://search.yahoo.co.jp/realtime/search?p=test",
        official_x,
        config,
        detected_on=date(2026, 7, 24),
    )
    assert len(x_cases) == 1
    assert x_cases[0].game_id == "dragon_ball_fusion_world"
    assert x_cases[0].canonical_product_key == "ST01"
    assert not x_alerts


def test_dragonball_classifier_excludes_non_box_products() -> None:
    config = load_config("sites.yaml")
    game = config.games["dragon_ball_fusion_world"]

    booster = classify_product(
        game,
        "ブースターパック BRIGHTNESS OF HOPE [FB11]",
        "1BOX 24パック入り",
    )
    starter = classify_product(
        game,
        "スタートデッキ サイヤ人の王子 [FS14]",
        "構築済みデッキ",
    )

    assert booster.is_box
    assert booster.canonical_product_key == "FB11"
    assert not starter.is_box
