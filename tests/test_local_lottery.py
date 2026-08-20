from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tcg_monitor.cli import (
    _lottery_description,
    _lottery_discord_description,
    _reuse_first_detection_start,
)
from tcg_monitor.config import load_config
from tcg_monitor.models import (
    Config,
    GameConfig,
    GameId,
    LotteryStartPolicy,
    Release,
    SourceConfig,
    SourceTier,
)
from tcg_monitor.parsers.local_lottery import (
    discover_livepocket_event_urls,
    is_hobby_station_news_page,
    parse_hobby_station_source,
    parse_livepocket_event,
    parse_yahoo_realtime,
    preserve_first_detection_start,
)
from tcg_monitor.parsers.pokemon_center import (
    discover_pokemon_center_news_urls,
    parse_pokemon_center_lottery,
)
from tcg_monitor.parsers.premium_bandai import (
    parse_nyuka_now_fullcomp,
    parse_nyuka_now_lottery_summary,
    parse_nyuka_now_premium_bandai,
)
from tcg_monitor.state import MonitorState


def _config() -> Config:
    pokemon = GameConfig(
        GameId.POKEMON,
        "ポケモンカードゲーム",
        "ポケカ",
        "",
        "",
        "",
        "",
        ["ポケモンカードゲーム", "ポケモンカード", "ポケカ"],
        ["拡張パック", "強化拡張パック", "ハイクラスパック"],
        [r"(?i)\b1?BOX\b"],
        ["スターターセット", "スタートデッキ", "デッキ", "セット", "大会"],
    )
    onepiece = GameConfig(
        GameId.ONE_PIECE,
        "ONE PIECEカードゲーム",
        "ワンピカード",
        "",
        "",
        "",
        "",
        ["ONE PIECEカードゲーム", "ワンピースカード", "ワンピカード"],
        ["ブースターパック", "エクストラブースター", "プレミアムブースター"],
        [r"(?i)\b1?BOX\b", r"\[(?:OP|EB|PRB)-\d{2}\]"],
        ["スタートデッキ", "スターターデッキ", "デッキ", "セット", "大会"],
        [r"\b(?P<code>OP-\d{2})\b", r"\b(?P<code>EB-\d{2})\b"],
    )
    return Config(
        2,
        "Asia/Tokyo",
        {},
        {"pokemon_card": pokemon, "one_piece_card": onepiece},
        {},
        [],
    )


def _source(source_id: str) -> SourceConfig:
    return SourceConfig(
        source_id,
        source_id,
        SourceTier.OFFICIAL_INDIRECT,
        {"pokemon_card": "verified", "one_piece_card": "prospective"},
        ["lottery_discovery"],
        True,
        ["https://example.com"],
    )


def test_livepocket_follows_only_box_lottery_details() -> None:
    html = """
    <main><ul>
      <li><a href="/e/pokemon-box"><h3>【抽選販売】ポケモンカードゲームMEGA
      拡張パック ストームエメラルダ</h3><p>日程 2026年7月31日〜8月2日</p></a></li>
      <li><a href="/e/starter"><h3>【抽選販売】ポケモンカードゲーム
      スターターセット イーブイex</h3></a></li>
      <li><a href="/e/onepiece-box"><h3>ホビーステーション「ONE PIECEカードゲーム
      ブースターパック 決戦の刻」抽選販売</h3></a></li>
      <li><a href="/e/concert"><h3>普通のコンサート</h3></a></li>
    </ul></main>
    """
    urls = discover_livepocket_event_urls(
        html,
        "https://livepocket.jp/event/search?word=test",
        _source("livepocket_hobby_station"),
        _config(),
    )
    assert urls == [
        "https://livepocket.jp/e/pokemon-box",
        "https://livepocket.jp/e/onepiece-box",
    ]


def test_livepocket_uses_application_period_not_event_date() -> None:
    html = """
    <main>
      <h1>【抽選販売】ポケモンカードゲームMEGA拡張パックストームエメラルダ</h1>
      <dl><dt>開催日</dt><dd>2026年7月31日(金)〜2026年8月2日(日)</dd></dl>
      <section><h2>詳細</h2><p>販売価格：1BOX 6,000円</p>
      <p>■応募期間：2026年7月11日(土)12：00頃～20日(月)23：59頃まで</p></section>
      <section><h2>受付・チケット情報</h2><p>販売受付期間 ：
      2026年7月11日(土) 12:00 〜2026年7月20日(月) 23:59</p></section>
    </main>
    """
    cases, releases, alerts = parse_livepocket_event(
        html,
        "https://livepocket.jp/e/gvyid",
        _source("livepocket_tsutaya_akebono"),
        _config(),
    )
    assert not releases
    assert not alerts
    assert cases[0].start_at == datetime(2026, 7, 11, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert cases[0].retailer_name == "TSUTAYAあけぼの店（石巻）"


def test_livepocket_future_onepiece_box_is_supported() -> None:
    html = """
    <h1>ホビーステーション「ONE PIECEカードゲーム ブースターパック 決戦の刻 [OP-16]」抽選販売</h1>
    <p>1BOX 24パック入り</p><p>■応募期間：2026年5月18日(月)12:00～5月20日(水)</p>
    <p>開催日 2026年5月30日</p>
    """
    cases, _, alerts = parse_livepocket_event(
        html,
        "https://livepocket.jp/e/onepiece",
        _source("livepocket_hobby_station"),
        _config(),
    )
    assert not alerts
    assert cases[0].game_id == "one_piece_card"
    assert cases[0].canonical_product_key == "OP-16"
    assert cases[0].start_at == datetime(2026, 5, 18, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


def test_hmv_livepocket_detects_current_onepiece_lottery() -> None:
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == "livepocket_hmv")
    event_url = "https://livepocket.jp/e/ilppk"
    search_html = f"""
    <main><a href="{event_url}"><h3>
    【HMVトレカショップ】ワンピースカード OP-17 世界最強の戦士 抽選販売
    </h3></a></main>
    """

    assert discover_livepocket_event_urls(
        search_html,
        source.discovery_urls[0],
        source,
        config,
    ) == [event_url]

    detail_html = """
    <main>
      <h1>【HMVトレカショップ】ワンピースカード OP-17 世界最強の戦士 抽選販売</h1>
      <p>抽選期間：2026年8月15日(土)13:00～8月17日(月)23:59まで</p>
      <p>購入期間：2026年8月22日(土)14:00～8月24日(月)閉店まで</p>
    </main>
    """
    cases, _, alerts = parse_livepocket_event(
        detail_html,
        event_url,
        source,
        config,
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "hmv"
    assert cases[0].game_id == "one_piece_card"
    assert cases[0].canonical_product_key == "OP-17"
    assert cases[0].start_at == datetime(
        2026, 8, 15, 13, 0, tzinfo=ZoneInfo("Asia/Tokyo")
    )


def test_livepocket_mixed_page_keeps_box_and_ignores_starter() -> None:
    html = """
    <h1>ポケモンカードゲーム 7/31発売新品商品 抽選購入権応募受付</h1>
    <p>・拡張パック「ストームエメラルダ」 お一人様1BOX</p>
    <p>・スターターセットex「イーブイex」 お一人様1個</p>
    <p>応募期間：2026年7月20日(月)10:00～7月26日(日)18:00</p>
    """
    cases, _, alerts = parse_livepocket_event(
        html,
        "https://livepocket.jp/e/fullcomp-test",
        _source("livepocket_fullcomp"),
        _config(),
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "fullcomp"
    assert "ストームエメラルダ" in cases[0].product_name


def test_pokemon_center_indexes_follow_only_lottery_articles() -> None:
    online_html = """
    <a href="/news/?id=20260720">ポケモンカードゲーム 抽選販売のお知らせ</a>
    <a href="/news/?id=20260719">ポケモンカードゲーム 新商品のお知らせ</a>
    """
    assert discover_pokemon_center_news_urls(
        online_html,
        "https://www.pokemoncenter-online.com/news/",
        _source("pokemon_center_online"),
    ) == ["https://www.pokemoncenter-online.com/news/?id=20260720"]

    store_html = """
    <a href="/ja/shop/common/news/202607/000393.html">
    7月31日発売 ポケモンカードゲーム関連商品の事前抽選について</a>
    """
    assert discover_pokemon_center_news_urls(
        store_html,
        "https://shop.pokemon.co.jp/ja/shop/common/news/",
        _source("pokemon_center_store"),
    ) == ["https://shop.pokemon.co.jp/ja/shop/common/news/202607/000393.html"]


def test_pokemon_center_store_uses_application_periods_not_result_dates() -> None:
    html = """
    <h1>7月31日（金）発売 ポケモンカードゲーム関連商品の事前抽選について</h1>
    <p>お知らせ 公開日：2026-07-10</p>
    <p>ポケモンカードゲーム MEGA 拡張パック「ストームエメラルダ」
    （お1人様20パックまで）</p>
    <h2>抽選お申し込み期間①</h2><p>7月15日（水）14時 ～ 7月17日（金）23時59分</p>
    <p>抽選結果発表日 7月21日（火）12時から順次</p>
    <h2>抽選お申し込み期間②</h2><p>7月22日（水）14時 ～ 7月24日（金）23時59分</p>
    <p>抽選結果発表日 7月28日（火）12時から順次</p>
    """
    cases, _, alerts = parse_pokemon_center_lottery(
        html,
        "https://shop.pokemon.co.jp/ja/shop/common/news/202607/000393.html",
        _source("pokemon_center_store"),
        _config(),
    )
    assert not alerts
    assert [case.start_at for case in cases] == [
        datetime(2026, 7, 15, 14, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        datetime(2026, 7, 22, 14, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
    ]
    assert all(case.start_at.day not in {21, 28} for case in cases)


def test_pokemon_center_online_is_separate_and_requires_box() -> None:
    html = """
    <h1>ポケモンカードゲーム 30周年記念商品の抽選販売</h1>
    <p>2026年7月20日</p>
    <p>ポケモンカードゲーム MEGA 拡張パック「30th CELEBRATION」BOX</p>
    <p>抽選応募受け付け期間：2026年8月3日（月）10時00分～8月5日（水）</p>
    <p>抽選結果発表日：2026年8月12日（水）</p>
    """
    cases, _, alerts = parse_pokemon_center_lottery(
        html,
        "https://www.pokemoncenter-online.com/news/?id=20260720",
        _source("pokemon_center_online"),
        _config(),
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "pokemon_center_online"
    assert cases[0].start_at == datetime(2026, 8, 3, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


def test_yahoo_start_is_first_detection_day_and_id_is_stable() -> None:
    html = """
    <div class="Tweet_TweetContainer__random">
      <p class="Tweet_body__random">📢ポケカ抽選販売のお知らせ📢
      『<a href="/realtime/search?p=product">#ストームエメラルダ</a>』
      抽選販売受付を開始します
      <a href="https://t.co/form123">customform.jp/form/input/250</a></p>
      <time><a href="https://x.com/TSUTAYA19392430/status/2077954547092521074?utm_source=test">7月17日</a></time>
    </div>
    """
    source = _source("yahoo_realtime_tsutaya_ichinoseki")
    first, _, alerts = parse_yahoo_realtime(
        html, "https://search.yahoo.co.jp/realtime/search", source, _config(), date(2026, 7, 19)
    )
    later, _, _ = parse_yahoo_realtime(
        html, "https://search.yahoo.co.jp/realtime/search", source, _config(), date(2026, 7, 21)
    )
    assert not alerts
    assert first[0].start_at == date(2026, 7, 19)
    assert first[0].extraction_method == "yahoo_realtime_detected_open"
    assert first[0].case_id == later[0].case_id
    assert first[0].official_url == "https://t.co/form123"
    assert first[0].source_url == ("https://x.com/TSUTAYA19392430/status/2077954547092521074")
    preserved = preserve_first_detection_start(
        later[0], {"start_at": first[0].start_at.isoformat()}
    )
    assert preserved.start_at == date(2026, 7, 19)


def test_torecaplaza55_official_x_detects_onepiece_web_lottery() -> None:
    html = """
    <div class="Tweet_TweetContainer__random">
      <p class="Tweet_body__random">【抽選販売】#ONEPIECEカードゲーム
      ブースターパック『決戦の刻』[OP-16] BOX
      抽選販売受付を開始しました
      <a href="https://t.co/torepla-form">応募ページ</a></p>
      <time><a href="https://x.com/torepla_ec/status/2077954547092521074">
      7月17日</a></time>
    </div>
    """

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_torecaplaza55"),
        _config(),
        date(2026, 7, 19),
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].game_id == "one_piece_card"
    assert cases[0].retailer_id == "torecaplaza55"
    assert cases[0].retailer_name == "トレカプラザ55通販店"
    assert cases[0].canonical_product_key == "OP-16"
    assert cases[0].start_at == date(2026, 7, 19)
    assert cases[0].official_url == "https://t.co/torepla-form"


def test_toreca_douraku_current_post_uses_detection_date() -> None:
    config = load_config("sites.yaml")
    source = next(
        item
        for item in config.sources
        if item.id == "yahoo_realtime_toreca_douraku_sendai"
    )
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">⭐️トレカ道楽 仙台駅前アーケード店⭐️
      《BOX抽選販売》ワンピースカードゲーム
      『最強の戦士』抽選販売開催！ 販売価格 お一人様1BOX 5,760円
      応募期間 本日から8月22日(土)まで。当選者へDMでご連絡します。</p>
      <time><a href="https://x.com/Dourakusendai/status/2084826013847130224">
      8月3日</a></time>
    </div>
    """

    cases, _, alerts = parse_yahoo_realtime(
        html,
        source.discovery_urls[2],
        source,
        config,
        date(2026, 8, 16),
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "toreca_douraku_sendai"
    assert cases[0].product_name == "最強の戦士"
    assert cases[0].start_at == date(2026, 8, 16)
    assert cases[0].extraction_method == "yahoo_realtime_detected_open"


def test_magi_sendai_actual_style_purchase_right_post_is_detected() -> None:
    config = load_config("sites.yaml")
    source = next(
        item for item in config.sources if item.id == "yahoo_realtime_magi_sendai"
    )
    known = Release(
        "pokemon_card",
        "拡張パック「ストームエメラルダ」",
        "拡張パック",
        "pokemon_card:storm-emerald",
        date(2026, 7, 31),
        None,
        "https://www.pokemon-card.com/products/",
        "https://www.pokemon-card.com/products/",
        SourceTier.OFFICIAL,
        "official_product_detail",
        "high",
    ).with_id()
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">✨ magi仙台店オープン記念企画 ✨
      《拡張パック ストームエメラルダ》の抽選応募ポストです。
      画像の注意事項をご確認いただき、ご了承頂ける方のみご応募ください。
      応募締切：8月31日(月)23:59</p>
      <time><a href="https://x.com/magi_sendai/status/2087022051567472976">
      8月10日</a></time>
    </div>
    """

    cases, _, alerts = parse_yahoo_realtime(
        html,
        source.discovery_urls[0],
        source,
        config,
        date(2026, 8, 16),
        known_releases=[known],
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "magi_sendai"
    assert cases[0].game_id == "pokemon_card"
    assert "ストームエメラルダ" in cases[0].product_name
    assert cases[0].start_at == date(2026, 8, 16)
    assert cases[0].extraction_method == "yahoo_realtime_detected_open"


def test_hmv_secondary_post_recovers_livepocket_lottery() -> None:
    config = load_config("sites.yaml")
    source = next(
        item for item in config.sources if item.id == "yahoo_realtime_hmv_secondary"
    )
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">HMVワンピースカード抽選受付中
      ONE PIECEカードゲーム ブースターパック「世界最強の戦士」[OP-17] 1BOX
      応募期間 8月15日(土)13:00～8月17日(月)23:59
      <a href="https://t.co/hmv-livepocket">応募ページ</a></p>
      <time><a href="https://x.com/gamegetnavi/status/2088522796976820235">
      8月15日</a></time>
    </div>
    """

    cases, _, alerts = parse_yahoo_realtime(
        html,
        source.discovery_urls[0],
        source,
        config,
        date(2026, 8, 16),
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "hmv"
    assert cases[0].game_id == "one_piece_card"
    assert cases[0].canonical_product_key == "OP-17"
    assert cases[0].source_tier == SourceTier.SECONDARY
    assert cases[0].official_url == "https://t.co/hmv-livepocket"
    assert cases[0].start_at == datetime(
        2026, 8, 15, 13, 0, tzinfo=ZoneInfo("Asia/Tokyo")
    )


def test_yahoo_starter_set_is_not_a_box_case() -> None:
    html = """
    <div class="Tweet_TweetContainer__random">
      <p class="Tweet_body__random">ポケカ スターターセット「イーブイex」抽選販売受付を開始</p>
      <time><a href="https://x.com/vw_1323/status/67890">7月18日</a></time>
    </div>
    """
    cases, _, _ = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_tsutaya_sanuma"),
        _config(),
        date(2026, 7, 19),
    )
    assert not cases


def test_mint_actual_style_body_uses_published_application_start_without_ocr() -> None:
    html = """
    <div class="Tweet_TweetContainer__aezGm">
      <p class="Tweet_body__3tH8T">【 <a href="/realtime/search?p=%23ポケカ">#ポケカ</a>
      <em>抽選</em>販売のお知らせ 】 ポケモンカードゲームMEGA 拡張パック
      「ストームエメラルダ<em>抽選</em>販売をいたします。
      受付期間：7/20(月)~7/27(月) 12時まで</p>
      <time><a href="https://x.com/mintsendai/status/2079008954995315120">1:02</a></time>
    </div>
    """
    ocr_calls: list[list[str]] = []

    def ocr_reader(urls: list[str]) -> str:
        ocr_calls.append(urls)
        return ""

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_mint_sendai"),
        _config(),
        date(2026, 7, 20),
        ocr_reader,
        {},
    )
    assert not alerts
    assert not ocr_calls
    assert cases[0].start_at == date(2026, 7, 20)
    assert "ストームエメラルダ" in cases[0].product_name
    assert cases[0].extraction_method == "yahoo_realtime_body_application_period"


def test_yahoo_image_ocr_is_conditional_and_cached() -> None:
    image_url = "https://rts-pctr.c.yimg.jp/test-image"
    html = f"""
    <div class="Tweet_TweetContainer__aezGm">
      <p class="Tweet_body__3tH8T">【ポケモンカードゲームの<em>抽選</em>販売のお知らせ】
      当店では7月31日発売予定のポケモンカード拡張パックは<em>抽選</em>販売と
      させていただきます。詳細は画像をご確認ください。</p>
      <img data-test="image" src="{image_url}">
      <time><a href="https://x.com/tsutayaichi0412/status/2077921225880317972">7月17日</a></time>
    </div>
    """
    cache: dict[str, str] = {}
    calls: list[list[str]] = []

    def ocr_reader(urls: list[str]) -> str:
        calls.append(urls)
        return "対象商品 拡張パック「ストームエメラルダ」 抽選受付期間：7/18(土)10:00～7/26(日)"

    source = _source("yahoo_realtime_tsutaya_ichinoseki_store")
    first, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        _config(),
        date(2026, 7, 20),
        ocr_reader,
        cache,
    )
    assert not alerts
    assert calls == [[image_url]]
    assert first[0].start_at == datetime(2026, 7, 18, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert "ストームエメラルダ" in first[0].product_name
    assert first[0].extraction_method == "yahoo_realtime_image_ocr_application_period"

    second, _, second_alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        _config(),
        date(2026, 7, 21),
        lambda _urls: (_ for _ in ()).throw(AssertionError("OCRを再実行してはいけない")),
        cache,
    )
    assert not second_alerts
    assert second[0].start_at == first[0].start_at


def test_cached_ocr_clears_pending_before_non_box_filter() -> None:
    image_url = "https://rts-pctr.c.yimg.jp/non-box-image"
    status_id = "2077921225880317972"
    status_url = f"https://x.com/tsutayaichi0412/status/{status_id}"
    html = f"""
    <div class="Tweet_TweetContainer__aezGm">
      <p class="Tweet_body__3tH8T">
      【ポケモンカードゲームの抽選販売】応募受付中。詳細は画像をご確認ください。
      </p>
      <img data-test="image" src="{image_url}">
      <time><a href="{status_url}">7月17日</a></time>
    </div>
    """
    pending: dict[str, object] = {
        status_url: {
            "source_id": "yahoo_realtime_tsutaya_ichinoseki_store",
            "attempts": 1,
            "last_error": "以前のOCR失敗",
        }
    }

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_tsutaya_ichinoseki_store"),
        _config(),
        date(2026, 7, 20),
        ocr_cache={
            status_url: (
                "ポケモンカードゲーム デッキシールド "
                "応募受付期間 7月17日10:00から"
            )
        },
        ocr_pending=pending,
    )

    assert not cases
    assert not alerts
    assert status_url not in pending


def test_yahoo_image_can_supply_game_before_body_classification() -> None:
    image_url = "https://rts-pctr.c.yimg.jp/yorozuya-morioka"
    html = f"""
    <div class="Tweet_TweetContainer__aezGm">
      <p class="Tweet_body__3tH8T">【抽選販売について】
      「ストームエメラルダ」発売に伴い、Xにて抽選販売と致します。
      【応募条件】①当アカウントをフォロー ②このポストをリポスト</p>
      <img data-test="image" src="{image_url}">
      <time><a href="https://x.com/yorozuya_card/status/2079734608745201729">8時間前</a></time>
    </div>
    """
    cache: dict[str, str] = {}
    calls: list[list[str]] = []

    def ocr_reader(urls: list[str]) -> str:
        calls.append(urls)
        return """ポケモンカードゲーム 抽選販売についてのお知らせ
        7/31発売のポケモンカード「ストームエメラルダ」
        7月27日 応募締め切り 7月28、29日 抽選・発表"""

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_yorozuya_morioka"),
        _config(),
        date(2026, 7, 22),
        ocr_reader,
        cache,
    )
    assert not alerts
    assert calls == [[image_url]]
    assert len(cases) == 1
    assert cases[0].game_id == "pokemon_card"
    assert cases[0].retailer_id == "yorozuya_morioka"
    assert cases[0].product_name == "ストームエメラルダ"
    assert cases[0].start_at == date(2026, 7, 22)
    assert cases[0].extraction_method == "yahoo_realtime_detected_open"
    assert cases[0].source_url in cache


def test_x_profile_mirror_catches_actual_yorozuya_post_when_ocr_fails() -> None:
    image_url = "https://pbs.twimg.com/media/HNzGQ0LaYAAXOAx.jpg"
    status_id = "2079755316506599865"
    html = f"""
    <div class="activity-posts">
      <div class="activity-group1">
        <div class="user-text3">
          <h4>萬屋盛岡店トレカコーナー <span>@yorozuya_card</span></h4>
          <span><a href="/yorozuya_card/status/{status_id}">9 hours ago</a></span>
        </div>
      </div>
      <div class="activity-descp"><p>【抽選販売について】
      「ストームエメラルダ」発売に伴い、Xにて抽選販売と致します。
      【応募条件】
      ①当アカウントをフォロー ②このポストをリポスト
      ③当選のDMが来た際に必要事項を返信できる方
      ④店頭にて期日までにご本人様が受取可能な方
      7/27 応募締切 7/28、29 抽選発表
      当選者の方へDMをお送り致します。</p></div>
      <img src="{image_url}" alt="yorozuya_card tweet picture">
      <a href="/yorozuya_card/status/{status_id}">View</a>
    </div>
    """
    known = Release(
        "pokemon_card",
        "ポケモンカードゲームMEGA 拡張パック「ストームエメラルダ」",
        "拡張パック",
        "pokemon_card:storm-emerald",
        date(2026, 7, 31),
        None,
        "https://www.pokemon-card.com/products/",
        "https://www.pokemon-card.com/products/",
        SourceTier.OFFICIAL,
        "official_product_detail",
        "high",
    ).with_id()
    calls: list[list[str]] = []

    def failing_ocr(urls: list[str]) -> str:
        calls.append(urls)
        raise RuntimeError("temporary OCR failure")

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://twstalker.com/yorozuya_card",
        _source("yahoo_realtime_yorozuya_morioka"),
        _config(),
        date(2026, 7, 22),
        failing_ocr,
        {},
        [known],
    )

    assert calls == [[image_url]]
    assert len(cases) == 1
    assert cases[0].game_id == "pokemon_card"
    assert cases[0].retailer_id == "yorozuya_morioka"
    assert cases[0].product_name == "ストームエメラルダ"
    assert cases[0].start_at == date(2026, 7, 22)
    assert cases[0].source_url == f"https://x.com/yorozuya_card/status/{status_id}"
    assert not alerts


def test_search_markup_spaces_do_not_turn_lottery_heading_into_product() -> None:
    html = """
    <div class="Tweet_TweetContainer__random">
      <p class="Tweet_body__random">【<em>抽選</em>販売について】
      「ストームエメラルダ」発売に伴い、Xにて<em>抽選</em>販売と致します。
      【応募条件】当アカウントをフォローし、このポストをリポスト</p>
      <time><a href="https://x.com/yorozuya_card/status/2079755316506599865">
      9時間前</a></time>
    </div>
    """
    known = Release(
        "pokemon_card",
        "拡張パック「ストームエメラルダ」",
        "拡張パック",
        "pokemon_card:storm-emerald",
        date(2026, 7, 31),
        None,
        "https://www.pokemon-card.com/products/",
        "https://www.pokemon-card.com/products/",
        SourceTier.OFFICIAL,
        "official_product_detail",
        "high",
    ).with_id()
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_yorozuya_morioka"),
        _config(),
        date(2026, 7, 22),
        known_releases=[known],
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].product_name == "ストームエメラルダ"


def test_x_search_does_not_relabel_stale_posts_as_new_lotteries() -> None:
    html = """
    <div class="activity-posts">
      <div class="activity-descp"><p>【抽選販売について】
      ポケモンカード「インフェルノX」発売に伴い、Xにて抽選販売と致します。
      応募条件をご確認ください。</p></div>
      <a href="/yorozuya_card/status/1969646425211617476">2025-09-21</a>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://twstalker.com/yorozuya_card",
        _source("yahoo_realtime_yorozuya_morioka"),
        _config(),
        date(2026, 7, 22),
    )
    assert not cases
    assert not alerts


def test_yahoo_image_first_classification_also_supports_onepiece() -> None:
    html = """
    <div class="PostCard__changedMarkup">
      <p>【抽選販売について】
      「世界最強の戦士」発売に伴い、Xにて抽選販売と致します。
      【応募条件】このポストをリポスト</p>
      <img src="https://rts-pctr.c.yimg.jp/onepiece-image">
      <time><a href="https://twitter.com/yorozuya_card/status/2079734608745201730">8時間前</a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_yorozuya_morioka"),
        _config(),
        date(2026, 7, 22),
        lambda _urls: "ONE PIECE カードゲーム ブースターパック「世界最強の戦士」[OP-17]",
        {},
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].game_id == "one_piece_card"
    assert cases[0].canonical_product_key == "OP-17"


def test_yahoo_image_first_classification_still_excludes_starter_products() -> None:
    html = """
    <div class="Tweet_TweetContainer__aezGm">
      <p class="Tweet_body__3tH8T">【抽選販売について】
      「イーブイex」発売に伴い、Xにて抽選販売と致します。</p>
      <img data-test="image" src="https://rts-pctr.c.yimg.jp/starter-image">
      <time><a href="https://x.com/yorozuya_card/status/2079734608745201731">8時間前</a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_yorozuya_morioka"),
        _config(),
        date(2026, 7, 22),
        lambda _urls: "ポケモンカードゲーム スターターセットex「イーブイex」",
        {},
    )
    assert not cases
    assert not alerts


def test_yahoo_unclassified_lottery_candidate_creates_alert() -> None:
    html = """
    <div class="Tweet_TweetContainer__aezGm">
      <p class="Tweet_body__3tH8T">【抽選販売について】
      「新商品」発売に伴い、Xにて抽選販売と致します。応募条件をご確認ください。</p>
      <time><a href="https://x.com/yorozuya_card/status/2079734608745201732">8時間前</a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_yorozuya_morioka"),
        _config(),
        date(2026, 7, 22),
    )
    assert not cases
    assert [alert.reason_code for alert in alerts] == ["yahoo_lottery_post_without_game"]


def test_catalog_aware_x_monitor_ignores_other_tcg_image_lottery() -> None:
    html = """
    <div class="activity-posts">
      <div class="activity-descp"><p>【抽選販売について】
      「Freedom Ascension」発売に伴い、Xにて抽選販売と致します。
      【応募条件】このポストをリポスト</p></div>
      <img src="https://pbs.twimg.com/media/other-game.jpg">
      <a href="/yorozuya_card/status/2078398111958069415">7月18日</a>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://twstalker.com/yorozuya_card",
        _source("yahoo_realtime_yorozuya_morioka"),
        _config(),
        date(2026, 7, 22),
        lambda _urls: (_ for _ in ()).throw(RuntimeError("OCR unavailable")),
        {},
        [],
    )
    assert not cases
    assert not alerts


def test_yahoo_falls_back_to_detection_day_when_image_has_no_start() -> None:
    html = """
    <div class="Tweet_TweetContainer__aezGm">
      <p class="Tweet_body__3tH8T">ポケカ<em>抽選</em>販売のお知らせ
      7月31日発売『<a href="/realtime/search?p=%23ストームエメラルダ">#ストームエメラルダ</a>』
      <em>抽選</em>販売受付を開始します</p>
      <img data-test="image" src="https://rts-pctr.c.yimg.jp/form-only">
      <time><a href="https://x.com/TSUTAYA19392430/status/2077954547092521074">7月17日</a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_tsutaya_ichinoseki"),
        _config(),
        date(2026, 7, 20),
        lambda _urls: "応募上の注意事項のみ",
        {},
    )
    assert not alerts
    assert cases[0].start_at == date(2026, 7, 20)
    assert cases[0].extraction_method == "yahoo_realtime_detected_open"


def test_mizusawa_mixed_box_and_starter_post_keeps_the_box() -> None:
    html = """
    <div class="Tweet_TweetContainer__aezGm">
      <p class="Tweet_body__3tH8T">抽選受付情報 7月31日発売 ポケモンカードゲームMEGA
      ・拡張パック【<a href="/realtime/search?p=%23ストームエメラルダ">#ストームエメラルダ</a>】
      ・スターターセット各種 は<em>抽選</em>販売とさせていただきます。
      詳細は画像をご確認ください。</p>
      <img data-test="image" src="https://rts-pctr.c.yimg.jp/mizusawa">
      <time><a href="https://x.com/WG_Mizusawa_TCG/status/2079014608745201729">7月20日</a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_torecano_mizusawa"),
        _config(),
        date(2026, 7, 20),
        lambda _urls: "抽選受付期間：7/21(火)～7/27(月)",
        {},
    )
    assert not alerts
    assert len(cases) == 1
    assert "ストームエメラルダ" in cases[0].product_name
    assert cases[0].start_at == date(2026, 7, 21)


def test_nyuka_now_premium_bandai_includes_older_resale_boxes() -> None:
    html = """
    <article>
      <h3>プレミアムバンダイ</h3>
      <p>対象商品</p>
      <ul>
        <li>ONE PIECEカードゲーム ブースターパック 神の島の冒険【OP-15】</li>
        <li>ONE PIECEカードゲーム 蒼海の七傑 OP-14</li>
        <li>ONE PIECEカードゲーム ブースターパック 受け継がれる意志【OP-13】</li>
      </ul>
      <p>抽選形式 WEB抽選受付</p>
      <p>開始日 7月17日(金)11:00</p>
      <a href="https://p-bandai.jp/brand/b0061/">応募ページ</a>
      <h3>DMM通販</h3><p>別の抽選</p>
    </article>
    """
    cases, _, alerts = parse_nyuka_now_premium_bandai(
        html,
        "https://nyuka-now.com/archives/97393",
        _source("nyuka_now_premium_bandai_onepiece"),
        _config(),
    )
    assert not alerts
    assert len(cases) == 3
    assert {case.canonical_product_key for case in cases} == {"OP-13", "OP-14", "OP-15"}
    assert all(
        case.start_at == datetime(2026, 7, 17, 11, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
        for case in cases
    )

def test_nyuka_now_summary_recovers_current_seagull_and_edion_boxes(
    tmp_path: Path,
) -> None:
    html = """
    <article>
      <h2>抽選・予約応募受付中のストア</h2>
      <h3>シーガル各店</h3>
      <table>
        <tr><th>対象商品</th><td><ul>
          <li>ポケモンカード スタートデッキ100 バトルコレクション</li>
          <li>ポケモンカード ストームエメラルダ</li>
        </ul></td></tr>
        <tr><th>開始日</th><td>2026年8月6日(木)10:00</td></tr>
      </table>

      <h2>近日受付開始予定のストア</h2>
      <h3>エディオン・トレカキャピタル各店</h3>
      <table>
        <tr><th>対象商品</th><td><ul>
          <li>ポケモンカード スタートデッキ100 バトルコレクション</li>
          <li>ポケモンカード ストームエメラルダ</li>
          <li>ポケモンカード メガブレイブ</li>
          <li>ポケモンカード メガシンフォニア</li>
        </ul></td></tr>
        <tr><th>開始日</th><td>2026年8月7日(金)10:00</td></tr>
        <tr><th>詳細ページ</th><td>
          <a href="https://edion-cp.com/pokeca082801/">エディオン</a>
          <a href="https://edion-cp.com/pokeca082802/">トレカキャピタル</a>
        </td></tr>
      </table>

      <h2>応募受付終了</h2>
      <h3>シーガル各店</h3>
      <table>
        <tr><th>対象商品</th><td>ポケモンカード 過去の拡張パック</td></tr>
        <tr><th>開始日</th><td>2026年7月1日(水)10:00</td></tr>
      </table>
    </article>
    """
    source = SourceConfig(
        "nyuka_now_fullcomp_livepocket",
        "入荷Now ポケカ抽選補完欄",
        SourceTier.SECONDARY,
        {"pokemon_card": "verified", "one_piece_card": "verified"},
        ["lottery_discovery"],
        True,
        ["https://nyuka-now.com/archives/2459"],
    )

    cases, releases, alerts = parse_nyuka_now_lottery_summary(
        html,
        "https://nyuka-now.com/archives/2459",
        source,
        _config(),
    )

    assert not releases
    assert not alerts
    assert len(cases) == 4
    assert len({case.case_id for case in cases}) == 4
    storm_cases = [case for case in cases if "ストームエメラルダ" in case.product_name]
    assert len(storm_cases) == 2
    assert len({case.canonical_product_key for case in storm_cases}) == 1
    assert {case.retailer_id for case in storm_cases} == {
        "seagull_sendai",
        "edion_online",
    }
    assert [case.retailer_id for case in cases].count("seagull_sendai") == 1
    assert [case.retailer_id for case in cases].count("edion_online") == 3
    assert all("スタートデッキ" not in case.product_name for case in cases)

    seagull = next(case for case in cases if case.retailer_id == "seagull_sendai")
    assert seagull.start_at == datetime(
        2026, 8, 6, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo")
    )
    assert seagull.official_url == "https://seagull.membercard.jp/lottery"

    edion_cases = [case for case in cases if case.retailer_id == "edion_online"]
    assert all(
        case.start_at == datetime(
            2026, 8, 7, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo")
        )
        for case in edion_cases
    )
    assert all(
        case.official_url == "https://edion-cp.com/pokeca082801/"
        for case in edion_cases
    )
    assert {case.product_name for case in edion_cases} == {
        "ポケモンカード ストームエメラルダ",
        "ポケモンカード メガブレイブ",
        "ポケモンカード メガシンフォニア",
    }

    edion_notification = _lottery_discord_description(edion_cases[0])
    assert (
        "応募予定ページ（受付開始前は未公開の場合あり）: "
        "https://edion-cp.com/pokeca082801/" in edion_notification
    )
    assert (
        "確認元ページ: https://nyuka-now.com/archives/2459"
        in edion_notification
    )
    edion_calendar_description = _lottery_description(
        edion_cases[0],
        datetime(2026, 8, 6, 19, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
    )
    assert (
        "応募予定ページ（受付開始前は未公開の場合あり）: "
        "https://edion-cp.com/pokeca082801/" in edion_calendar_description
    )

    legacy_edion_id = "legacy-edion-shared-url-key"
    state = MonitorState(tmp_path / "edion-state.json")
    state.data["seen_cases"][legacy_edion_id] = {
        "game_id": "pokemon_card",
        "retailer_id": "edion_online",
        "product_name": "ポケモンカード メガシンフォニア",
        "canonical_product_key": "pokeca082801",
        "start_at": "2026-08-07T10:00:00+09:00",
        "official_url": "https://edion-cp.com/pokeca082801/",
        "source_url": "https://nyuka-now.com/archives/2459",
    }
    state.data["delivery_journal"][f"lottery:started:{legacy_edion_id}"] = {
        "updated_at": "2026-08-06T09:50:00+00:00"
    }
    state.data["calendar_sync"][f"lottery:{legacy_edion_id}"] = {
        "event_id": "existing-mega-symphonia-event",
        "payload_hash": "legacy",
    }

    migrated = {
        case.product_name: state.migrate_case_identity(case) for case in edion_cases
    }
    assert migrated["ポケモンカード ストームエメラルダ"] is None
    assert migrated["ポケモンカード メガブレイブ"] is None
    mega_symphonia = next(
        case for case in edion_cases if "メガシンフォニア" in case.product_name
    )
    assert migrated[mega_symphonia.product_name] == legacy_edion_id
    assert state.calendar_case_identity(mega_symphonia.case_id) == legacy_edion_id
    assert (
        f"lottery:started:{mega_symphonia.case_id}"
        in state.data["delivery_journal"]
    )

    wrong_seagull_id = "wrong-onepiece-seagull"
    wrong_state = MonitorState(tmp_path / "seagull-state.json")
    wrong_state.data["seen_cases"][wrong_seagull_id] = {
        "game_id": "pokemon_card",
        "retailer_id": "seagull_sendai",
        "product_name": (
            "ONE PIECEカードゲーム ブースターパック 世界最強の戦士【OP-17】"
        ),
        "canonical_product_key": "lottery",
        "start_at": "2026-08-02T10:00:00+09:00",
        "official_url": "https://seagull.membercard.jp/lottery",
        "source_url": "https://nyuka-now.com/archives/97393",
    }
    assert wrong_state.migrate_case_identity(seagull) is None
    assert wrong_seagull_id in wrong_state.data["seen_cases"]


def test_nyuka_now_priority_retailers_ignore_onepiece_summary_page() -> None:
    html = """
    <article>
      <h2>抽選・予約応募受付中のストア</h2>
      <h3>シーガル各店</h3>
      <table>
        <tr><th>対象商品</th><td>
          ONE PIECEカードゲーム ブースターパック 世界最強の戦士【OP-17】
        </td></tr>
        <tr><th>開始日</th><td>2026年8月2日(日)10:00</td></tr>
      </table>
    </article>
    """
    source = SourceConfig(
        "nyuka_now_fullcomp_livepocket",
        "入荷Now ポケカ抽選補完欄",
        SourceTier.SECONDARY,
        {"pokemon_card": "verified", "one_piece_card": "verified"},
        ["lottery_discovery"],
        True,
        ["https://nyuka-now.com/archives/97393"],
    )

    cases, releases, alerts = parse_nyuka_now_lottery_summary(
        html,
        "https://nyuka-now.com/archives/97393",
        source,
        _config(),
    )

    assert not cases
    assert not releases
    assert not alerts


def test_yamada_secondary_detects_app_only_lottery_with_medium_confidence() -> None:
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">ヤマダ電機
      ワンピースカード ブースターパック「世界最強の戦士」[OP-17] BOX抽選販売
      応募期間：2026年8月1日(土) 10:00〜8月3日(月) 23:59</p>
      <time><a href="https://x.com/gamegetnavi/status/2082116147403784398">
      7月28日</a></time>
    </div>
    """
    source = SourceConfig(
        "yahoo_realtime_yamada_secondary",
        "ヤマダデンキ抽選情報",
        SourceTier.SECONDARY,
        {"pokemon_card": "prospective", "one_piece_card": "prospective"},
        ["secondary_lottery_discovery"],
        True,
        ["https://search.yahoo.co.jp/realtime/search"],
    )

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        _config(),
        date(2026, 7, 30),
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "yamada_denki"
    assert cases[0].start_at == datetime(
        2026, 8, 1, 10, 0, tzinfo=ZoneInfo("Asia/Tokyo")
    )
    assert cases[0].source_tier == SourceTier.SECONDARY
    assert cases[0].confidence == "medium"
    assert cases[0].official_url == (
        "https://www.yamada-denki.jp/service/pointservice/digital-kaiin.html"
    )
    assert cases[0].extraction_method == (
        "yahoo_realtime_secondary_body_application_period"
    )


def test_yamada_secondary_reports_postponement_without_false_calendar_case() -> None:
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">『世界最強の戦士』OP-17ワンピースカード
      抽選販売延期。ヤマダ電機は本日23時から抽選販売を実施予定でしたが、
      突然延期を発表。</p>
      <time><a href="https://x.com/gamegetnavi/status/2082116147403784398">
      7月28日</a></time>
    </div>
    """
    source = SourceConfig(
        "yahoo_realtime_yamada_secondary",
        "ヤマダデンキ抽選情報",
        SourceTier.SECONDARY,
        {"pokemon_card": "prospective", "one_piece_card": "prospective"},
        ["postponement_monitoring"],
        True,
        ["https://search.yahoo.co.jp/realtime/search"],
    )

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        _config(),
        date(2026, 7, 30),
    )

    assert not cases
    assert [alert.reason_code for alert in alerts] == [
        "lottery_postponed_or_cancelled"
    ]
    assert alerts[0].game_id == "one_piece_card"
    assert "世界最強の戦士" in alerts[0].change_summary
    assert "延期" in alerts[0].change_summary


def test_secondary_profile_fallback_ignores_other_retailers() -> None:
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">ゲオでワンピースカード
      ブースターパック「世界最強の戦士」BOX抽選販売。
      応募期間：2026年8月3日 11:00〜8月6日 17:59</p>
      <time><a href="https://x.com/gamegetnavi/status/2082116147403784398">
      7月28日</a></time>
    </div>
    """
    source = SourceConfig(
        "yahoo_realtime_yamada_secondary",
        "ヤマダデンキ抽選情報",
        SourceTier.SECONDARY,
        {"pokemon_card": "prospective", "one_piece_card": "prospective"},
        ["secondary_lottery_discovery"],
        True,
        ["https://twstalker.com/gamegetnavi"],
    )

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://twstalker.com/gamegetnavi",
        source,
        _config(),
        date(2026, 7, 30),
    )

    assert not cases
    assert not alerts

def test_kojima_secondary_ignores_multi_retailer_roundup_post() -> None:
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">ポケカ最新作『ストームエメラルダ』
      『スターターセットex』予約・抽選受付情報
      【抽選受付中の店舗一覧】Amazon コジマ DMM キデイランド
      ポケモンカードの抽選情報はこちら</p>
      <a href="https://t.co/roundup">抽選リスト</a>
      <time><a href="https://x.com/gamegetnavi/status/2080645250255827125">
      7月25日</a></time>
    </div>
    """
    source = SourceConfig(
        "yahoo_realtime_kojima_secondary",
        "コジマ抽選情報",
        SourceTier.SECONDARY,
        {"pokemon_card": "prospective"},
        ["secondary_lottery_discovery"],
        True,
        ["https://search.yahoo.co.jp/realtime/search"],
    )

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        _config(),
        date(2026, 7, 30),
    )

    assert not cases
    assert not alerts


def test_secondary_source_without_explicit_start_never_uses_detection_date() -> None:
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">コジマでポケモンカード
      拡張パック「ストームエメラルダ」のBOX抽選販売を実施中。</p>
      <time><a href="https://x.com/gamegetnavi/status/2080490402503643152">
      7月24日</a></time>
    </div>
    """
    source = SourceConfig(
        "yahoo_realtime_kojima_secondary",
        "コジマ抽選情報",
        SourceTier.SECONDARY,
        {"pokemon_card": "prospective"},
        ["secondary_lottery_discovery"],
        True,
        ["https://search.yahoo.co.jp/realtime/search"],
    )

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        _config(),
        date(2026, 7, 30),
    )

    assert not cases
    assert not alerts


def test_result_notice_is_not_treated_as_new_lottery_start() -> None:
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">【抽選販売の当選連絡は本日以降】
      ポケカ新弾「ストームエメラルダ」BOX抽選について、
      当選メールを順次お送りします。</p>
      <time><a href="https://x.com/DMM_Myca/status/2082586970123866217">
      7月30日</a></time>
    </div>
    """

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_dmm_myca"),
        _config(),
        date(2026, 7, 30),
    )

    assert not cases
    assert not alerts

def test_result_only_image_is_not_reported_as_missing_product() -> None:
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">DMMマイカ ポケカ新弾の抽選販売についてご案内</p>
      <img src="https://pbs.twimg.com/media/result-notice.jpg">
      <time><a href="https://x.com/DMM_Myca/status/2082586970123866217">
      7月30日</a></time>
    </div>
    """

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_dmm_myca"),
        _config(),
        date(2026, 7, 30),
        lambda _urls: (
            "応募期間 2026年7月23日～7月28日 "
            "当選者のみにメールにて連絡 2026年7月29日～7月30日 "
            "購入・受取 2026年8月7日以降"
        ),
        {},
    )

    assert not cases
    assert not alerts

def test_hobby_station_official_news_catches_current_box_lottery() -> None:
    html = """
    <section>
      <h2>【2026.08.04】ポケモンカードゲームMEGA 30th CELEBRATION</h2>
      <p>ポケモンカードゲームMEGA 30th CELEBRATION
      プレミアムデッキセット エーフィ・ブラッキーを抽選販売します。
      抽選受付ページリンク：<a href="https://livepocket.jp/e/s8waw">応募</a>
      ■応募期間：2026年8月4日(火)12：00～8月6日(木)23：59まで</p>
      <p>ポケモンカードゲームMEGA 拡張パック「30th CELEBRATION」を抽選販売します。
      当選者は2BOXまで購入できます。
      抽選受付ページリンク：<a href="https://livepocket.jp/e/m3_6v">応募</a>
      ■応募期間：2026年8月4日(火)12：00～8月6日(木)23：59まで</p>
    </section>
    """
    url = "https://www.hbst.net/category/news/"
    source = _source("livepocket_hobby_station")

    assert is_hobby_station_news_page(source.id, url)
    cases, releases, alerts = parse_hobby_station_source(
        html,
        url,
        source,
        _config(),
    )

    assert not releases
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "hobby_station"
    assert cases[0].product_name == "拡張パック「30th CELEBRATION」"
    assert cases[0].start_at == datetime(
        2026, 8, 4, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo")
    )
    assert cases[0].official_url == "https://livepocket.jp/e/m3_6v"
    assert cases[0].source_url == url
    assert cases[0].source_tier == SourceTier.OFFICIAL
    assert cases[0].extraction_method == "hobby_station_official_application_period"


def test_tsutaya_akebono_official_x_is_an_independent_livepocket_fallback() -> None:
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">【商品情報】2026年7月31日（金）発売の
      ポケモンカードゲーム MEGA拡張パックストームエメラルダは
      LivePocketでの抽選販売となります。詳細は画像をご覧ください。</p>
      <img src="https://rts-pctr.c.yimg.jp/akebono-lottery.jpg">
      <time><a href="https://x.com/AKEBONOtoreka/status/2075777096211956194">
      7月11日</a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_tsutaya_akebono"),
        _config(),
        date(2026, 7, 11),
        lambda _urls: "抽選受付期間：2026年7月11日(土)12:00～7月19日(日)23:59",
        {},
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "tsutaya_akebono"
    assert cases[0].retailer_name == "TSUTAYAあけぼの店（石巻）"
    assert "ストームエメラルダ" in cases[0].product_name
    assert cases[0].start_at == datetime(
        2026, 7, 11, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo")
    )


def test_nyuka_now_fullcomp_recovers_unindexed_livepocket_event() -> None:
    html = """
    <article>
      <h3>フルコンプ 一部店舗</h3>
      <figure><table>
        <tr><th>対象商品</th><td><ul>
          <li>ポケモンカード メガブレイブ</li>
          <li>ポケモンカード メガシンフォニア</li>
        </ul></td></tr>
        <tr><th>抽選形式</th><td>WEB抽選受付（当選者には店頭販売）</td></tr>
        <tr><th>開始日</th><td>7月27日(月)16:00</td></tr>
        <tr><th>詳細ページ</th><td>
          <a href="https://livepocket.jp/e/im27p">フルコンプ 一部店舗の詳細ページ</a>
        </td></tr>
      </table></figure>
      <h3>フルコンプ 一部店舗</h3>
      <figure><table>
        <tr><th>対象商品</th><td>ポケモンカード スターターセットex イーブイex</td></tr>
        <tr><th>開始日</th><td>7月27日(月)16:00</td></tr>
        <tr><th>詳細ページ</th><td>
          <a href="https://livepocket.jp/e/starter">詳細ページ</a>
        </td></tr>
      </table></figure>
      <h3>別店舗</h3>
    </article>
    """
    source = SourceConfig(
        "nyuka_now_fullcomp_livepocket",
        "入荷Now フルコンプLivePocket抽選欄",
        SourceTier.SECONDARY,
        {"pokemon_card": "verified"},
        ["lottery_discovery"],
        True,
        ["https://nyuka-now.com/archives/2459"],
    )
    cases, _, alerts = parse_nyuka_now_fullcomp(
        html,
        "https://nyuka-now.com/archives/2459",
        source,
        _config(),
    )

    assert not alerts
    assert len(cases) == 2
    assert {case.product_name for case in cases} == {
        "ポケモンカード メガブレイブ",
        "ポケモンカード メガシンフォニア",
    }
    assert all(case.retailer_id == "fullcomp" for case in cases)
    assert all(case.official_url == "https://livepocket.jp/e/im27p" for case in cases)
    assert all(
        case.start_at == datetime(2026, 7, 27, 16, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
        for case in cases
    )
    assert all(case.source_tier == SourceTier.SECONDARY for case in cases)


def test_yahoo_deadline_only_ocr_is_alert_not_calendar_case() -> None:
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      ポケカ 拡張パック「ストームエメラルダ」1BOXの抽選販売。
      応募期間・応募方法などの詳細は画像をご確認ください。
      </p>
      <img src="https://rts-pctr.c.yimg.jp/mandai-deadline-only">
      <time><a href="https://x.com/mandaifurukaw3/status/2080941127419441184">
      7月25日</a></time>
    </div>
    """

    cases, releases, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_mandai_furukawa"),
        _config(),
        date(2026, 7, 25),
        lambda _urls: (
            "ポケモンカードゲーム 拡張パック「ストームエメラルダ」 "
            "応募期間 2026年7月30日（木）18:00まで "
            "当選者に7月30日19時頃DMにて連絡"
        ),
        {},
    )

    assert not cases
    assert not releases
    assert [alert.reason_code for alert in alerts] == [
        "application_deadline_without_start"
    ]


def test_configured_policy_uses_first_detection_next_day(tmp_path: Path) -> None:
    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      【ワンピ抽選販売のお知らせ】
      8月22日（土）発売『世界最強の戦士【OP-17】』
      抽選販売のWEB受付を開始します。
      </p>
      <img src="https://rts-pctr.c.yimg.jp/sanuma-op17-lottery">
      <time><a href="https://x.com/vw_1323/status/2086988926141825281">
      8月11日</a></time>
    </div>
    """
    ocr_text = """
    抽選販売のお知らせ
    8/22(土)発売 ONE PIECEカードゲーム
    ブースターパック「世界最強の戦士」[OP-17] 1BOX
    【予約受付期間】
    8月19日(水) 23:59まで
    【当選者発表】
    8月20日(木) X（旧Twitter）にて発表
    【ご購入期間】
    発売日より2日間（8月23日閉店まで）
    """
    source = replace(
        _source("yahoo_realtime_tsutaya_sanuma"),
        lottery_start_policy=LotteryStartPolicy.FIRST_DETECTION_NEXT_DAY,
    )

    first, releases, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        _config(),
        date(2026, 8, 11),
        lambda _urls: ocr_text,
        {},
    )

    assert not releases
    assert not alerts
    assert len(first) == 1
    assert first[0].retailer_id == "tsutaya_sanuma"
    assert first[0].start_at == date(2026, 8, 12)
    assert first[0].extraction_method == "yahoo_realtime_detected_next_day"
    assert first[0].confidence == "low"

    later, _, later_alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        source,
        _config(),
        date(2026, 8, 12),
        lambda _urls: ocr_text,
        {},
    )
    assert not later_alerts
    assert later[0].case_id == first[0].case_id
    assert later[0].start_at == date(2026, 8, 13)

    state = MonitorState(tmp_path / "sanuma-state.json")
    state.data["seen_cases"][first[0].case_id] = {
        **first[0].__dict__,
        "start_at": "2026-08-20",
        "extraction_method": "yahoo_realtime_image_ocr_application_period",
    }
    state.data["delivery_journal"][f"lottery:started:{first[0].case_id}"] = {
        "status": "complete",
        "updated_at": "2026-08-11T02:59:53.618454+00:00",
    }

    repaired = _reuse_first_detection_start(state, later[0])

    assert repaired.start_at == date(2026, 8, 12)
    assert state.data["delivery_journal"][
        f"lottery:started:{first[0].case_id}"
    ]["status"] == "complete"


def test_tsutaya_ichinoseki_open_notice_survives_winner_notes_in_image() -> None:
    """Recover the Aug. 7 OP-17 start even when OCR drops range separators."""

    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      【ONE PIECEカードゲーム の抽選販売のお知らせ】
      当店では8月22日発売予定のONE PIECEカードゲームは
      抽選販売とさせていただきます。
      抽選日程、対象商品などの詳細は画像をご確認ください。
      </p>
      <img src="https://rts-pctr.c.yimg.jp/ichinoseki-op17-lottery">
      <time><a href="https://x.com/tsutayaichi0412/status/2085531368847442214">
      8月7日</a></time>
    </div>
    """

    ocr_text = """
    トレーディングカード 抽選販売についてのご案内
    8月22日発売
    ONE PIECE ブースターパック
    世界最強の戦士OP17
    抽選受付期間
    2026年8月7日(金) 12時20時
    2026年8月8日(土)9日(日) 10時19時
    当選番号掲示期間 2026年8月22日(土)～2026年8月24日(月)
    ご購入期間 2026年8月22日(土)～2026年8月24日(月)
    当選権利の第三者への譲渡はできません。
    当選者さまご自身でご購入をお願いします。
    """

    cases, releases, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_tsutaya_ichinoseki_store"),
        _config(),
        date(2026, 8, 8),
        lambda _urls: ocr_text,
        {},
    )

    assert not releases
    assert not alerts
    assert len(cases) == 1
    case = cases[0]
    assert case.retailer_id == "tsutaya_ichinoseki_store"
    assert case.retailer_name == "TSUTAYA一関店"
    assert "世界最強の戦士" in case.product_name
    assert case.start_at == datetime(
        2026, 8, 7, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo")
    )
    assert case.source_url == (
        "https://x.com/tsutayaichi0412/status/2085531368847442214"
    )
    assert case.extraction_method == "yahoo_realtime_image_ocr_application_period"


def test_image_open_notice_is_read_even_when_body_mentions_winners() -> None:
    """A generic official post must reach OCR before result-only filtering."""

    html = """
    <div class="Tweet_TweetContainer__test">
      <p class="Tweet_body__test">
      BOX抽選販売のお知らせ。当選者のみご購入いただけます。
      日程と商品は画像をご確認ください。
      </p>
      <img src="https://rts-pctr.c.yimg.jp/official-open-lottery">
      <time><a href="https://x.com/tsutayaichi0412/status/2085531368847442214">
      8月7日</a></time>
    </div>
    """

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_tsutaya_ichinoseki_store"),
        _config(),
        date(2026, 8, 8),
        lambda _urls: (
            "ONE PIECEカードゲーム ブースターパック 世界最強の戦士 OP-17 "
            "抽選受付期間 2026年8月7日(金)12時～20時 "
            "当選者さまご自身でご購入ください"
        ),
        {},
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].start_at == datetime(
        2026, 8, 7, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo")
    )
