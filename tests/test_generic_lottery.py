from datetime import date, datetime

from tcg_monitor.config import load_config
from tcg_monitor.parsers.generic import discover_geo_news_urls, parse_generic


def _source(source_id: str):  # type: ignore[no-untyped-def]
    config = load_config("sites.yaml")
    return config, next(source for source in config.sources if source.id == source_id)


def test_release_date_in_geo_title_is_not_lottery_start() -> None:
    config, source = _source("geo")
    html = """
    <article>
      <h2>2026/07/24 8月22日(土)発売
      「ONE PIECEカードゲーム ブースターパック 世界最強の戦士」
      抽選販売受付のお知らせ</h2>
    </article>
    """

    cases, _, alerts = parse_generic(html, "https://geo-online.co.jp/news/", source, config)

    assert not cases
    assert any(alert.reason_code == "lottery_text_without_start" for alert in alerts)


def test_geo_index_discovers_card_box_lottery_detail_only() -> None:
    config, source = _source("geo")
    html = """
    <ul>
      <li><a href="/news/775">2026/07/24 8月22日(土)発売
      「ONE PIECEカードゲーム ブースターパック 世界最強の戦士」
      抽選販売受付のお知らせ</a></li>
      <li><a href="/news/999">ゲーム機本体の抽選販売受付のお知らせ</a></li>
      <li><a href="/news/998">ポケモンカードゲーム 大会のお知らせ</a></li>
    </ul>
    """

    assert discover_geo_news_urls(
        html,
        "https://geo-online.co.jp/news/",
        source,
        config,
    ) == ["https://geo-online.co.jp/news/775"]


def test_labelled_application_date_wins_over_earlier_release_date() -> None:
    config, source = _source("geo")
    html = """
    <article>
      <h2>8月22日(土)発売
      「ONE PIECEカードゲーム ブースターパック 世界最強の戦士」
      抽選販売受付のお知らせ</h2>
      <p>応募期間は「8/3(月) 11:00 ～ 8/6(木) 17:59」まで</p>
    </article>
    """

    cases, _, alerts = parse_generic(
        html,
        "https://geo-online.co.jp/news/123/",
        source,
        config,
    )

    assert len(cases) == 1
    assert isinstance(cases[0].start_at, datetime)
    assert cases[0].start_at.date() == date(2026, 8, 3)
    assert cases[0].start_at.hour == 11
    assert not alerts


def test_geo_nested_article_keeps_product_and_application_period_together() -> None:
    config, source = _source("geo")
    html = """
    <main>
      <article>
        <div><h1>7月31日(金)発売「ポケモンカードゲーム MEGA
        拡張パック ストームエメラルダ」抽選販売について</h1></div>
        <div><p>発売日当日分は抽選販売のみとさせていただきます。</p></div>
        <div><p>応募期間は「7/13(月) 11:00 ～ 7/16(木) 17:59」
        までとなります。</p></div>
      </article>
    </main>
    """

    cases, _, alerts = parse_generic(
        html,
        "https://geo-online.co.jp/news/770",
        source,
        config,
    )

    assert len(cases) == 1
    assert cases[0].start_at == datetime.fromisoformat("2026-07-13T11:00:00+09:00")
    assert not alerts


def test_source_specific_start_label_is_loaded_and_used() -> None:
    config, source = _source("yodobashi")
    assert "お申込み受付期間" in source.start_labels
    html = """
    <article>
      <h2>8月22日(土)発売 ポケモンカードゲーム 拡張パック「テスト」抽選販売</h2>
      <p>お申込み受付期間：2026年7月24日(金) 10時00分から</p>
    </article>
    """

    cases, _, alerts = parse_generic(
        html,
        "https://limited.yodobashi.com/",
        source,
        config,
    )

    assert len(cases) == 1
    assert isinstance(cases[0].start_at, datetime)
    assert cases[0].start_at.date() == date(2026, 7, 24)
    assert not alerts


def test_release_date_after_unpublished_application_label_is_not_used() -> None:
    config, source = _source("geo")
    html = """
    <article>
      <h2>ONE PIECEカードゲーム ブースターパック「世界最強の戦士」抽選販売</h2>
      <p>応募受付期間は後日お知らせします。発売日：2026年8月22日(土)</p>
    </article>
    """

    cases, _, alerts = parse_generic(
        html,
        "https://geo-online.co.jp/news/124/",
        source,
        config,
    )

    assert not cases
    assert any(alert.reason_code == "lottery_text_without_start" for alert in alerts)
