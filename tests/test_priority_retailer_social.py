from __future__ import annotations

from datetime import date

import pytest

from tcg_monitor.config import load_config
from tcg_monitor.models import (
    Config,
    GameConfig,
    GameId,
    GameSupport,
    SourceConfig,
    SourceTier,
)
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.source_priority import merge_lotteries


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
        ["スターターセット", "スタートデッキ", "デッキ", "セット"],
    )
    one_piece = GameConfig(
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
        ["スタートデッキ", "スターターデッキ", "デッキ", "セット"],
        [
            r"\b(?P<code>OP-\d{2})\b",
            r"\b(?P<code>EB-\d{2})\b",
            r"\b(?P<code>PRB-\d{2})\b",
        ],
    )
    return Config(
        2,
        "Asia/Tokyo",
        {"implausible_past_days": 365},
        {"pokemon_card": pokemon, "one_piece_card": one_piece},
        {},
        [],
    )


def _source(source_id: str) -> SourceConfig:
    game_id = (
        "one_piece_card"
        if source_id
        in {
            "yahoo_realtime_dmm_onepiece_secondary",
            "yahoo_realtime_amazon_onepiece_secondary",
            "yahoo_realtime_amazon_gamegetnavi_secondary",
        }
        else "pokemon_card"
    )
    tier = (
        SourceTier.SECONDARY
        if source_id.endswith("_secondary")
        else SourceTier.OFFICIAL_INDIRECT
    )
    return SourceConfig(
        source_id,
        source_id,
        tier,
        {game_id: GameSupport.VERIFIED},
        ["lottery_discovery"],
        True,
        ["https://example.com"],
    )


@pytest.mark.parametrize(
    ("source_id", "account", "retailer_id"),
    [
        ("yahoo_realtime_hobbylink_japan", "hobbylink_jp", "hobbylink_japan"),
        ("yahoo_realtime_seven_net", "7_netshopping", "seven_net"),
        ("yahoo_realtime_nojima_online", "ENETJP", "nojima_online"),
        (
            "yahoo_realtime_dragonstar_online",
            "ds_ecommerce",
            "dragonstar_online",
        ),
        ("yahoo_realtime_dmm_tsuhan", "DMM_tsuhan", "dmm_tsuhan"),
        ("yahoo_realtime_dmm_myca", "DMM_Myca", "dmm_myca"),
        ("yahoo_realtime_edion", "edion_PR", "edion_online"),
        ("yahoo_realtime_famima", "famima_now", "famima_online"),
    ],
)
def test_priority_retailer_accounts_accept_entry_period_wording(
    source_id: str,
    account: str,
    retailer_id: str,
) -> None:
    html = f"""
    <div class="Tweet_TweetContainer__random">
      <p class="Tweet_body__random">ポケモンカードゲーム
      拡張パック「ストームエメラルダ」BOX 抽選販売
      エントリー受付期間：2026年7月20日(月)10:00～
      2026年7月24日(金)23:59</p>
      <time><a href="https://x.com/{account}/status/2077954547092521074">
      7月20日</a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source(source_id),
        _config(),
        date(2026, 7, 20),
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == retailer_id
    assert cases[0].start_at.isoformat() == "2026-07-20T10:00:00+09:00"


def test_hobbylink_generic_x_notice_is_covered_by_official_article_source() -> None:
    html = """
    <div class="Tweet_TweetContainer__random">
      <p class="Tweet_body__random">
      ポケモンカードゲームの抽選販売受付を開始しました。詳細はこちら
      </p>
      <time><a href="https://x.com/hobbylink_jp/status/2077553622284734825">
      7月20日</a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_hobbylink_japan"),
        _config(),
        date(2026, 7, 20),
    )
    assert not cases
    assert not alerts


def test_hobbylink_bracketed_game_name_is_not_mistaken_for_a_box() -> None:
    html = """
    <div class="Tweet_TweetContainer__random">
      <p class="Tweet_body__random">
      【ポケモンカード】抽選販売受付を開始しました。詳細はこちら
      </p>
      <time><a href="https://x.com/hobbylink_jp/status/2077350263795732964">
      7月20日</a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_hobbylink_japan"),
        _config(),
        date(2026, 7, 20),
    )
    assert not cases
    assert not alerts


def test_other_retailer_generic_x_notice_still_requests_manual_check() -> None:
    html = """
    <div class="Tweet_TweetContainer__random">
      <p class="Tweet_body__random">
      ポケモンカードゲームの抽選販売受付を開始しました。詳細はこちら
      </p>
      <time><a href="https://x.com/7_netshopping/status/2077553622284734825">
      7月20日</a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_seven_net"),
        _config(),
        date(2026, 7, 20),
    )
    assert not cases
    assert [alert.reason_code for alert in alerts] == [
        "yahoo_lottery_post_without_product"
    ]



def test_dmm_secondary_announcement_recovers_campaign_with_deadline_only() -> None:
    html = """
    <div class="Tweet_TweetContainer__random">
      <p class="Tweet_body__random">【販売情報】
      DMM通販で「ONE PIECEカードゲーム」の抽選受付開始
      受付期間 8月17日(月)15時まで
      ✓応募ページ ・決戦の刻 ・EGGHEAD CRISIS ・Heroines Edition</p>
      <time><a href="https://x.com/onepiecenyuka/status/2086699130622247096">
      8月10日</a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_dmm_onepiece_secondary"),
        _config(),
        date(2026, 8, 10),
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "dmm_tsuhan"
    assert cases[0].game_id == "one_piece_card"
    assert cases[0].product_name == "ONE PIECEカードゲーム DMM通販 抽選対象BOX"
    assert cases[0].start_at == date(2026, 8, 10)
    assert cases[0].extraction_method == "yahoo_realtime_secondary_announcement_date"
    assert cases[0].official_url.startswith("https://www.dmm.com/")


def test_hobby_search_secondary_announcement_covers_direct_site_403() -> None:
    html = """
    <div class="Tweet_TweetContainer__random">
      <p class="Tweet_body__random">【ポケカ抽選販売】
      ホビーサーチにて拡張パック「アビスアイ」の抽選販売受付開始
      受付期間 7月5日(日)23時59分まで</p>
      <time><a href="https://x.com/PokeGetInfoMain/status/2072972286232346961">
      7月3日</a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_hobby_search_secondary"),
        _config(),
        date(2026, 7, 3),
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "hobby_search"
    assert cases[0].product_name == "拡張パック「アビスアイ」"
    assert cases[0].start_at == date(2026, 7, 3)
    assert cases[0].extraction_method == "yahoo_realtime_secondary_announcement_date"
    assert cases[0].official_url == "https://www.1999.co.jp/list/3352/7/1"



def test_dmm_secondary_reservation_label_is_not_used_as_product_name() -> None:
    html = """
    <div class="Tweet_TweetContainer__random">
      <p class="Tweet_body__random">DMM通販 ONE PIECEカードゲーム
      【予約】エクストラブースター [OP-15] 抽選受付開始
      受付期間 8月17日(月)15時まで</p>
      <time><a href="https://x.com/onepiecenyuka/status/2086699130622247096">
      8月10日</a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_dmm_onepiece_secondary"),
        _config(),
        date(2026, 8, 10),
    )
    assert not alerts
    assert len(cases) == 1
    assert "予約" not in cases[0].product_name
    assert "OP-15" in cases[0].product_name


def test_secondary_deadline_only_old_post_is_ignored_without_error() -> None:
    html = """
    <div class="Tweet_TweetContainer__random">
      <p class="Tweet_body__random">DMM通販 ONE PIECEカードゲーム
      ブースターパック「神の島の冒険」[OP-15] 抽選受付中
      受付期間 8月1日(土)23時59分まで</p>
      <time><a href="https://x.com/onepiecenyuka/status/2076912032662823413">
      7月14日</a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_dmm_onepiece_secondary"),
        _config(),
        date(2026, 8, 10),
    )
    assert not cases
    assert not alerts


def test_amazon_invitation_post_recovers_direct_asin_and_seen_date() -> None:
    html = """
    <div class="Tweet_TweetContainer__random">
      <p class="Tweet_body__random">【販売情報】
      Amazonにて「ONE PIECEカードゲーム エクストラブースター
      ONE PIECE Heroines Edition vol.2【EB-05】」の
      招待リクエスト受付が開始しました。</p>
      <a href="https://t.co/example"
         title="https://www.amazon.co.jp/dp/B0HB3JQ6P4?tag=affiliate-22">
         amazon.co.jp/dp/B0HB3JQ6P4?tag=affiliate-22</a>
      <time><a href="https://x.com/onepiecenyuka/status/2087125238991696167">
      8月11日</a></time>
    </div>
    """

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_amazon_onepiece_secondary"),
        _config(),
        date(2026, 8, 12),
    )

    assert not alerts
    assert len(cases) == 1
    case = cases[0]
    assert case.retailer_id == "amazon_jp"
    assert case.canonical_product_key == "EB-05"
    assert case.start_at == date(2026, 8, 11)
    assert case.official_url == "https://www.amazon.co.jp/dp/B0HB3JQ6P4"
    assert case.extraction_method == "yahoo_realtime_amazon_invitation_seen"
    assert case.confidence == "medium"


def test_amazon_invitation_paths_share_one_asin_identity() -> None:
    def post(account: str, status_id: str) -> str:
        return f"""
        <div class="Tweet_TweetContainer__random">
          <p class="Tweet_body__random">Amazon招待リクエスト受付開始
          ONE PIECEカードゲーム エクストラブースター
          「ONE PIECE Heroines Edition vol.2」[EB-05] BOX</p>
          <a href="https://t.co/example">
          amazon.co.jp/dp/B0HB3JQ6P4?ref_=social</a>
          <time><a href="https://x.com/{account}/status/{status_id}">8月11日</a></time>
        </div>
        """

    first, _, first_alerts = parse_yahoo_realtime(
        post("onepiecenyuka", "2087125238991696167"),
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_amazon_onepiece_secondary"),
        _config(),
        date(2026, 8, 12),
    )
    second, _, second_alerts = parse_yahoo_realtime(
        post("gamegetnavi", "2087126668196601899"),
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_amazon_gamegetnavi_secondary"),
        _config(),
        date(2026, 8, 12),
    )

    assert not first_alerts
    assert not second_alerts
    assert first[0].case_id == second[0].case_id


def test_repeated_amazon_posts_without_resolved_asin_are_one_case() -> None:
    def post(status_id: str, short_url: str, prefix: str) -> str:
        return f"""
        <div class="Tweet_TweetContainer__random">
          <p class="Tweet_body__random">{prefix}
          エクストラブースター ONE PIECE Heroines Edition vol.2【EB-05】
          Amazon 招待リクエスト受付開始</p>
          <a href="{short_url}">{short_url}</a>
          <time><a href="https://x.com/onepiecenyuka/status/{status_id}">
          8月11日</a></time>
        </div>
        """

    first, _, first_alerts = parse_yahoo_realtime(
        post("2087124342010491311", "https://t.co/tsRvSXw4cs", "ONE PIECE カードゲーム"),
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_amazon_onepiece_secondary"),
        _config(),
        date(2026, 8, 12),
    )
    second, _, second_alerts = parse_yahoo_realtime(
        post("2087125238991696167", "https://t.co/mQkn1sqex5", "ワンピースカード"),
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_amazon_onepiece_secondary"),
        _config(),
        date(2026, 8, 12),
    )

    assert not first_alerts
    assert not second_alerts
    assert len(first) == len(second) == 1
    assert first[0].official_url != second[0].official_url
    assert first[0].case_id == second[0].case_id
    merged, alerts = merge_lotteries(first + second)
    assert len(merged) == 1
    assert not alerts


def test_amazon_secondary_ignores_non_invitation_sale_post() -> None:
    html = """
    <div class="Tweet_TweetContainer__random">
      <p class="Tweet_body__random">AmazonでONE PIECEカードゲーム
      エクストラブースター「ONE PIECE Heroines Edition vol.2」[EB-05]
      通常予約を受付中です。</p>
      <time><a href="https://x.com/onepiecenyuka/status/2087125238991696167">
      8月11日</a></time>
    </div>
    """

    cases, _, alerts = parse_yahoo_realtime(
        html,
        "https://search.yahoo.co.jp/realtime/search",
        _source("yahoo_realtime_amazon_onepiece_secondary"),
        _config(),
        date(2026, 8, 12),
    )

    assert not cases
    assert not alerts


def test_amazon_source_configuration_keeps_manual_and_social_modes_separate() -> None:
    by_id = {source.id: source for source in load_config("sites.yaml").sources}

    assert not by_id["amazon_jp"].enabled
    assert by_id["amazon_jp"].render_mode.value == "http_no_challenge_bypass"
    assert by_id["amazon_jp"].expected_elements == [
        "product_title",
        "sold_by_amazon_if_visible",
    ]
    for source_id in (
        "yahoo_realtime_amazon_onepiece_secondary",
        "yahoo_realtime_amazon_gamegetnavi_secondary",
    ):
        assert not by_id[source_id].enabled
        assert by_id[source_id].render_mode.value == "http"
        assert "amazon_asin_link" in by_id[source_id].expected_elements


def test_nonofficial_social_accounts_cannot_trigger_normal_notifications() -> None:
    by_id = {source.id: source for source in load_config("sites.yaml").sources}

    for source_id in (
        "yahoo_realtime_yamada_secondary",
        "yahoo_realtime_kojima_secondary",
        "yahoo_realtime_amazon_onepiece_secondary",
        "yahoo_realtime_amazon_gamegetnavi_secondary",
        "yahoo_realtime_dmm_onepiece_secondary",
        "yahoo_realtime_hobby_search_secondary",
    ):
        assert not by_id[source_id].enabled
