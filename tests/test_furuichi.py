from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from tcg_monitor.config import load_config
from tcg_monitor.parsers.furuichi import (
    discover_furuichi_lottery_urls,
    furuichi_index_has_target_lottery,
    parse_furuichi_lottery_detail,
)
from tcg_monitor.pipeline import run_pipeline


def _source():  # type: ignore[no-untyped-def]
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == "furuichi_official_lottery")
    return config, source


def test_furuichi_index_follows_only_supported_box_lotteries() -> None:
    html = """
    <main>
      <ul>
        <li>2026/08/11 お知らせ
          <a href="/news/news_information/tl0822">
          ＯＮＥ　ＰＩＥＣＥカードゲーム　ブースターパック
          世界最強の戦士〖ＯＰ－１７〗抽選受付について</a>
        </li>
        <li><a href="/news/news_information/open0821">
          ふるいち新店舗オープンのお知らせ</a></li>
        <li><a href="/news/news_information/deck0820">
          ONE PIECEカードゲーム スタートデッキ 抽選受付について</a></li>
      </ul>
    </main>
    """
    config, source = _source()

    assert discover_furuichi_lottery_urls(
        html,
        "https://www.furu1.net/news/news_information.html",
        source,
        config,
    ) == ["https://www.furu1.net/news/news_information/tl0822"]

    broken_link_html = html.replace(
        "/news/news_information/tl0822",
        "javascript:void(0)",
    )
    assert furuichi_index_has_target_lottery(
        broken_link_html,
        source,
        config,
    )


def test_furuichi_detail_reads_application_period_from_official_image_once() -> None:
    html = """
    <html><head><title>抽選受付について | 古本市場</title></head>
    <body><main>
      <h2>ＯＮＥ　ＰＩＥＣＥカードゲーム　ブースターパック
      世界最強の戦士〖ＯＰ－１７〗抽選受付について</h2>
      <img src="/storage/news/news_information/tl0822/20260811lpg.jpg">
    </main></body></html>
    """
    config, source = _source()
    cache: dict[str, str] = {}
    cache_meta: dict[str, object] = {}
    calls: list[list[str]] = []

    def ocr_reader(urls: list[str]) -> str:
        calls.append(urls)
        return (
            "抽選応募受付期間 2026年8月11日(火)～"
            "2026年8月16日(日)23:00まで\n"
            "当選発表 2026年8月20日(木)23時頃"
        )

    url = "https://www.furu1.net/news/news_information/tl0822"
    cases, releases, alerts = parse_furuichi_lottery_detail(
        html,
        url,
        source,
        config,
        detected_on=date(2026, 8, 12),
        ocr_reader=ocr_reader,
        ocr_cache=cache,
        ocr_cache_meta=cache_meta,
    )

    assert not releases
    assert not alerts
    assert len(cases) == 1
    case = cases[0]
    assert case.retailer_id == "furuichi"
    assert case.canonical_product_key == "OP-17"
    assert case.start_at == date(2026, 8, 11)
    assert case.end_at == datetime(2026, 8, 16, 23, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert case.extraction_method == "furuichi_official_image_application_period"
    assert calls == [["https://www.furu1.net/storage/news/news_information/tl0822/20260811lpg.jpg"]]
    assert cache[url].startswith("抽選応募受付期間")
    assert url in cache_meta

    def unexpected_ocr(_urls: list[str]) -> str:
        raise AssertionError("cached official article image must not be OCRed again")

    cached_cases, _, cached_alerts = parse_furuichi_lottery_detail(
        html,
        url,
        source,
        config,
        detected_on=date(2026, 8, 13),
        ocr_reader=unexpected_ocr,
        ocr_cache=cache,
        ocr_cache_meta=cache_meta,
    )
    assert not cached_alerts
    assert cached_cases[0].case_id == case.case_id


def test_furuichi_generic_mixed_game_article_reads_each_box_from_image() -> None:
    html = """
    <html><head>
      <meta property="article:published_time" content="2026-09-01T00:00:00+09:00">
    </head><body><main>
      <h1>ポケモンカードゲーム　ドラゴンボールスーパーカードゲーム抽選受付について</h1>
      <img src="/storage/news/news_information/pdl20260901/20260901lp.jpg">
    </main></body></html>
    """
    # Actual Japanese Tesseract output contains these characteristic errors.
    ocr_text = """
    2026 年9月12 日発売予定
    「 ドラゴンドールスー カードゲームフュージョンワールド
    ブースタッやク BRICHTNESS OF HOPE [FB11l/
    2026 年9 月 16 日発売予定
    「ポケモンカードゲーム MEGA 30th CELEBRATION
    プレミアムデッキセット エーフィ・ブラッキー]
    「ポケモンカードゲーム MEGA 拡張パック 30th CELEBRATION]
    (1) 受付方法・期間
    ・受付期間 : 2026年9月6日 (日) 23:00 まで
    """
    config, source = _source()

    cases, releases, alerts = parse_furuichi_lottery_detail(
        html,
        "https://www.furu1.net/news/news_information/pdl20260901",
        source,
        config,
        detected_on=date(2026, 9, 2),
        ocr_reader=lambda _urls: ocr_text,
    )

    assert not releases
    assert not alerts
    assert len(cases) == 2
    assert {case.game_id for case in cases} == {
        "pokemon_card",
        "dragon_ball_fusion_world",
    }
    assert {case.canonical_product_key for case in cases} >= {"FB11"}
    dragon_ball = next(
        case for case in cases if case.game_id == "dragon_ball_fusion_world"
    )
    assert dragon_ball.product_name.endswith("BRIGHTNESS OF HOPE [FB11]")
    assert all("デッキセット" not in case.product_name for case in cases)
    assert all(
        case.end_at == datetime(2026, 9, 6, 23, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
        for case in cases
    )


def test_furuichi_index_follows_generic_supported_game_lottery_article() -> None:
    html = """
    <main><article>
      <a href="/news/news_information/pdl20260901">
      ポケモンカードゲーム　ドラゴンボールスーパーカードゲーム抽選受付について
      </a>
    </article></main>
    """
    config, source = _source()

    assert discover_furuichi_lottery_urls(
        html,
        "https://www.furu1.net/news/news_information.html",
        source,
        config,
    ) == ["https://www.furu1.net/news/news_information/pdl20260901"]


def test_furuichi_deadline_only_image_still_notifies_while_open() -> None:
    html = """
    <html><head>
      <meta property="article:published_time" content="2026-08-11T00:00:00+09:00">
    </head><body><main>
      <h1>ONE PIECEカードゲーム ブースターパック
      世界最強の戦士〖OP-17〗抽選受付について</h1>
      <img src="https://furu1.net/storage/news/news_information/tl0822/notice.jpg">
    </main></body></html>
    """
    config, source = _source()
    cases, _, alerts = parse_furuichi_lottery_detail(
        html,
        "https://furu1.net/news/news_information/tl0822",
        source,
        config,
        detected_on=date(2026, 8, 12),
        ocr_reader=lambda _urls: "抽選受付期間 ～2026年8月16日(日)23:00まで",
    )

    assert not alerts
    assert cases[0].start_at == date(2026, 8, 11)
    assert cases[0].end_at == datetime(2026, 8, 16, 23, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert cases[0].extraction_method == "furuichi_official_open_detected"
    assert cases[0].confidence == "low"


def test_furuichi_ocr_failure_is_a_visible_monitor_alert() -> None:
    html = """
    <h1>ONE PIECEカードゲーム ブースターパック
    世界最強の戦士〖OP-17〗抽選受付について</h1>
    <img src="/storage/news/news_information/tl0822/notice.jpg">
    """
    config, source = _source()

    def fail_ocr(_urls: list[str]) -> str:
        raise RuntimeError("simulated OCR failure")

    cases, _, alerts = parse_furuichi_lottery_detail(
        html,
        "https://www.furu1.net/news/news_information/tl0822",
        source,
        config,
        ocr_reader=fail_ocr,
    )

    assert not cases
    assert [alert.reason_code for alert in alerts] == ["furuichi_image_ocr_failed"]


def test_pipeline_follows_furuichi_index_and_uses_cached_official_ocr() -> None:
    config, _ = _source()
    article_url = "https://www.furu1.net/news/news_information/tl0822"
    cases, releases, alerts = run_pipeline(
        config,
        "tests/fixtures",
        {"furuichi_official_lottery"},
        ocr_cache={article_url: ("抽選応募受付期間 2026年8月11日(火)～2026年8月16日(日)23:00まで")},
    )

    assert not releases
    assert not alerts
    assert len(cases) == 1
    assert cases[0].canonical_product_key == "OP-17"
    assert cases[0].end_at == datetime(2026, 8, 16, 23, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
