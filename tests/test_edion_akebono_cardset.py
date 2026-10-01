"""実際の告知の書き方で、監視先・画像の時刻・全国枠を検証する。"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from tcg_monitor.cli import _lottery_discord_description
from tcg_monitor.config import load_config
from tcg_monitor.parsers.local_lottery import _application_start, parse_yahoo_realtime

JST = ZoneInfo("Asia/Tokyo")


def test_akebono_cardset_ocr_keeps_exact_time_and_one_campaign() -> None:
    config = load_config("sites.yaml")
    source = next(s for s in config.sources if s.id == "yahoo_realtime_tsutaya_akebono")
    html = """
    <div class="Tweet_TweetContainer__example">
      <p class="Tweet_body__example">【商品情報】ポケモンカードゲーム
      30th CELEBRATION カードセット9種はLivePocketでの抽選販売となります。
      詳細は下記をご覧下さいませ。ご了承の上、お申し込みください。</p>
      <img src="https://pbs.twimg.com/media/akebono.jpg">
      <time><a href="https://x.com/AKEBONOtoreka/status/2105497694307578309">12:19</a></time>
    </div>
    """
    # 元画像の認識結果では00が0oになり、日付までしか読めなかった。
    # 色を強調した画像の結果では、同じ応募期間を正確に認識できた。
    ocr = """
    抽選期間 : 202e年10月1日 (木) 12 : 0o頃から10月4日 (日) 23 : 59頃まで
    当選発表 : 2026年10月5日 (月) から10月6日 (火) の間予定
    販売期間 : 2026年1月6日 (金) から10月8日 (日) まで
    拡張パック 30th CELEBRATION カードセット9種
    抽選期間 : 2026年10月1日 (木) 12 : 00頃から10月4日 (日) 23 : 59頃まで
    当選発表 : 2026年10月5日 (月) から10月6日 (火) の間予定
    販売期間 : 2026年10月16日 (金) から10月18日 (日) まで
    """
    cases, _, alerts = parse_yahoo_realtime(
        html, source.discovery_urls[0], source, config, date(2026, 10, 1),
        ocr_reader=lambda _: ocr,
    )
    assert not alerts
    assert len(cases) == 1
    case = cases[0]
    assert case.canonical_product_key == "pokemon_30th_cardset"
    assert case.product_category == "カードセット"
    assert case.start_at == datetime(2026, 10, 1, 12, tzinfo=JST)
    assert case.end_at == datetime(2026, 10, 4, 23, 59, tzinfo=JST)
    assert "受付開始: 2026/10/01 12:00" in _lottery_discord_description(case)


def test_ocr_cannot_replace_application_day_with_later_purchase_day() -> None:
    assert _application_start(
        "抽選期間：2026年10月1日から10月4日まで。"
        "販売期間：2026年10月16日10:00から10月18日まで。"
    ) == date(2026, 10, 1)


@pytest.mark.parametrize("slug", ["poke101601", "poke101602", "pokeca101601"])
def test_edion_national_campaign_is_read_from_official_tcg_account(slug: str) -> None:
    config = load_config("sites.yaml")
    source = next(s for s in config.sources if s.id == "yahoo_realtime_edion")
    assert source.parser_options["account"] == "Trecapi_namba"
    assert all("edion_PR" not in url for url in source.discovery_urls)
    html = f"""
    <div class="Tweet_TweetContainer__example">
      <p class="Tweet_body__example">ポケモンカードゲーム
      30th CELEBRATION カードセット9種の抽選受付を開始！
      抽選受付期間：10月2日(金)10:00から10月4日(日)23:59まで。</p>
      <a href="https://t.co/campaign">edion-cp.com/{slug}</a>
      <time><a href="https://x.com/Trecapi_namba/status/2105497694307578309">10月1日</a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html, source.discovery_urls[0], source, config, date(2026, 10, 1),
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "edion_online"
    assert cases[0].official_url == f"https://edion-cp.com/{slug}"
    assert cases[0].start_at == datetime(2026, 10, 2, 10, tzinfo=JST)


def test_edion_published_national_notice_recovers_expanded_application_url() -> None:
    config = load_config("sites.yaml")
    source = next(s for s in config.sources if s.id == "yahoo_realtime_edion")
    # 9/11に公式アカウントが実際に出した告知。応募先は本文リンクの表示名にある。
    html = """
    <div class="Tweet_TweetContainer__example">
      <p class="Tweet_body__example">遊戯王「ORIGINAL ARTWORK COLLECTION」の
      抽選受付を開始！ 抽選受付期間 9月11日(金)～9月13日(日)
      当選発表 9月25日(金) 応募条件:当社各種会員様限定
      店舗掲示QR、または下記URLからご応募可能です。</p>
      <a href="https://t.co/vNFLQDKjXY">edion-cp.com/yugioh092602</a>
      <time><a href="https://x.com/Trecapi_namba/status/2098263296189358480">9月11日</a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html, source.discovery_urls[0], source, config, date(2026, 9, 11),
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].product_name == "ORIGINAL ARTWORK COLLECTION"
    assert cases[0].official_url == "https://edion-cp.com/yugioh092602"
    assert cases[0].start_at == date(2026, 9, 11)


def test_edion_image_notice_recovers_official_application_url() -> None:
    config = load_config("sites.yaml")
    source = next(s for s in config.sources if s.id == "yahoo_realtime_edion")
    html = """
    <div class="Tweet_TweetContainer__example">
      <p class="Tweet_body__example">ポケモンカードゲーム
      30th CELEBRATION カードセット 抽選販売を開始。詳細は画像をご確認ください。</p>
      <img src="https://pbs.twimg.com/media/edion.jpg">
      <time><a href="https://x.com/Trecapi_namba/status/2105497694307578309">10月1日</a></time>
    </div>
    """
    cases, _, alerts = parse_yahoo_realtime(
        html, source.discovery_urls[0], source, config, date(2026, 10, 1),
        ocr_reader=lambda _: (
            "抽選受付期間：10月2日10:00から10月4日23:59まで "
            "https://edion-cp.com/poke101602"
        ),
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].official_url == "https://edion-cp.com/poke101602"
    assert cases[0].start_at == datetime(2026, 10, 2, 10, tzinfo=JST)


def test_edion_local_draw_does_not_become_national_campaign() -> None:
    config = load_config("sites.yaml")
    source = next(s for s in config.sources if s.id == "yahoo_realtime_edion")
    html = """
    <div class="Tweet_TweetContainer__example">
      <p class="Tweet_body__example">なんば本店限定 ポケモンカードゲーム
      30th CELEBRATION カードセット 抽選販売
      抽選受付期間：10月2日10:00から10月4日23:59まで。</p>
      <a href="https://t.co/local">edion-cp.com/trecapiopen1001</a>
      <time><a href="https://x.com/Trecapi_namba/status/2105497694307578309">10月1日</a></time>
    </div>
    """
    diagnostics: dict[str, int] = {}
    cases, _, alerts = parse_yahoo_realtime(
        html, source.discovery_urls[0], source, config, date(2026, 10, 1),
        diagnostics=diagnostics,
    )
    assert not cases
    assert not alerts
    assert diagnostics["application_url_outside_scope"] == 1
