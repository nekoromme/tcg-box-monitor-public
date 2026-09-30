from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tcg_monitor.config import load_config
from tcg_monitor.http_client import FetchResult
from tcg_monitor.parsers.official_retailers import parse_onepiece_official_shop
from tcg_monitor.parsers.retailer_lottery import retailer_lottery_index_matches_scope
from tcg_monitor.pipeline import run_pipeline
from tcg_monitor.state import MonitorState

CONFIG = load_config("sites.yaml")
SOURCES = {source.id: source for source in CONFIG.sources}
NEWS_URL = (
    "https://bandainamco-am.co.jp/official_shop/onepiece-cardgame/"
    "news/important/20260508.html"
)
INDEX_URL = "https://parks2.bandainamco-am.co.jp/category/EL/"


@pytest.mark.parametrize(
    ("heading_tag", "heading"),
    [("h1", "ブースターパックの販売方法について"),
     ("h2", "ONE PIECEカードゲーム関連商品の購入制限について")],
)
def test_permanent_purchase_rules_are_not_incomplete_draws(
    heading_tag: str, heading: str,
) -> None:
    html = f"""
    <header><h1><img alt="企業ロゴ"></h1></header>
    <article><{heading_tag}>{heading}</{heading_tag}>
      <p>ブースターパックはBOX事前抽選販売。購入時に本人確認を行います。</p>
    </article>
    """
    cases, releases, alerts = parse_onepiece_official_shop(
        html, NEWS_URL, SOURCES["onepiece_official_shop_news"], CONFIG,
    )
    assert not cases and not releases and not alerts


def test_real_draw_uses_article_heading_and_period_after_empty_logo_heading() -> None:
    html = """
    <header><h1><img alt="企業ロゴ"></h1>
      <p>応募受付期間：2026年8月1日10:00～8月2日23:59</p></header>
    <article><h1>ブースターパック 世界最強の戦士【OP-17】事前抽選について</h1>
      <p>BOX抽選 申込受付期間：2026年9月11日10:00～9月15日23:59</p>
      <a href="https://parks2.bandainamco-am.co.jp/category/ECCL00000054/">応募</a>
    </article>
    """
    cases, _, alerts = parse_onepiece_official_shop(
        html, NEWS_URL, SOURCES["onepiece_official_shop_news"], CONFIG,
    )
    assert not alerts and len(cases) == 1
    assert cases[0].product_name == "ブースターパック 世界最強の戦士【OP-17】"
    assert cases[0].canonical_product_key == "OP-17"
    assert cases[0].start_at == datetime(2026, 9, 11, 10, tzinfo=ZoneInfo("Asia/Tokyo"))


def test_actual_product_without_application_period_still_warns() -> None:
    html = """
    <header><h1></h1></header>
    <article><h1>ブースターパック 世界最強の戦士【OP-17】抽選販売</h1>
      <p>1BOX購入権の抽選を行います。</p></article>
    """
    cases, _, alerts = parse_onepiece_official_shop(
        html, NEWS_URL, SOURCES["onepiece_official_shop_news"], CONFIG,
    )
    assert not cases
    assert [alert.reason_code for alert in alerts] == ["official_store_start_missing"]
    assert alerts[0].title == "ブースターパック 世界最強の戦士【OP-17】抽選販売"


def test_policy_page_updated_with_real_draw_is_still_detected() -> None:
    html = """
    <article><h1>ブースターパックの販売方法について</h1>
      <p>世界最強の戦士【OP-17】1BOX抽選販売</p>
      <p>申込受付期間：2026年9月11日10:00～9月15日23:59</p></article>
    """
    cases, _, alerts = parse_onepiece_official_shop(
        html, NEWS_URL, SOURCES["onepiece_official_shop_news"], CONFIG,
    )
    assert not alerts and len(cases) == 1


class _IndexFetcher:
    def __init__(self, html: str) -> None:
        self.html = html

    def fetch(self, url: str, **_kwargs: str | None) -> FetchResult:
        assert url == INDEX_URL
        return FetchResult(url, 200, self.html, {})


@pytest.mark.parametrize(
    "target_store_notice",
    ["", "【仙台店】たまごっち事前抽選販売", "【仙台店】ONE PIECE大会抽選"],
)
def test_other_store_draw_and_local_event_do_not_trigger_missing_link_alert(
    tmp_path: Path, target_store_notice: str,
) -> None:
    # Keep the local event and the other store's card in separate product
    # cards, even when one outer article wraps the entire national index.
    html = f"""
    <article><ul>
      <li><a href="/category/EL/hakata.html">【博多店】抽選申込
        ONE PIECEカードゲーム ブースターパック【OP-17】購入権</a></li>
      <li><a href="/category/EL/sendai-event.html">{target_store_notice}</a></li>
    </ul></article>
    """
    source = SOURCES["namco_onepiece_official_shop_miyagi"]
    assert not retailer_lottery_index_matches_scope(html, source, CONFIG)
    state = MonitorState.load(tmp_path / "state.json")
    cases, _, alerts = run_pipeline(
        replace(CONFIG, sources=[source]), http_fetcher=_IndexFetcher(html),
        monitor_state=state,
    )
    assert not cases and not alerts
    assert state.data["monitors"][source.id]["outcome"] == "success"


def test_target_store_draw_with_broken_detail_url_still_warns(tmp_path: Path) -> None:
    html = """
    <article><a href="javascript:void(0)">【宮城名取店】抽選申込
      ONE PIECEカードゲーム ブースターパック【OP-17】購入権</a></article>
    """
    source = SOURCES["namco_onepiece_official_shop_miyagi"]
    cases, _, alerts = run_pipeline(
        replace(CONFIG, sources=[source]), http_fetcher=_IndexFetcher(html),
        monitor_state=MonitorState.load(tmp_path / "state.json"),
    )
    assert not cases
    assert [alert.reason_code for alert in alerts] == ["retailer_lottery_detail_link_missing"]
