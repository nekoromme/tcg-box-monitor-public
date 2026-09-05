from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from tcg_monitor.config import load_config
from tcg_monitor.http_client import FetchResult
from tcg_monitor.parsers.retailer_lottery import parse_retailer_lottery_detail
from tcg_monitor.pipeline import run_pipeline
from tcg_monitor.state import MonitorState

CONFIG = load_config("sites.yaml")
SOURCE = next(s for s in CONFIG.sources if s.id == "rakuten_books")
INDEX = SOURCE.discovery_urls[0]
DETAIL = "https://books.rakuten.co.jp/rb/18595282/"
# Minimal reconstruction of the observed official product/period fields.
# Unrelated header and footer terms must not turn a genuine BOX into a non-BOX.
HTML = """<h1>楽天ブックス</h1>
<h1>ポケモンカードゲーム MEGA 拡張パック 30th CELEBRATION</h1>
<section><p>発売日：2026年09月16日</p></section>
<div>抽選受付期間：2026/08/27(木) 10:00 〜 2026/08/30(日) 23:59<br>
当選者販売期間：2026/09/14(月) 10:00 〜 2026/09/18(金) 09:59</div>
<p>20パック入り</p><footer>キャンペーンや大会に関する一般の注意</footer>"""


@freeze_time("2026-08-27 12:00:00+09:00")
def test_rakuten_index_follows_box_detail_and_pairs_separate_period(tmp_path):
    pages = {
        INDEX: f"""<h1>ポケモンカードゲーム 抽選商品</h1><ul><li>
    <a href="{DETAIL}"><img alt="ポケモンカードゲーム 拡張パック 30th CELEBRATION"></a>
    </li></ul><a href="https://unrelated.example/rb/18595282/">ポケカ拡張パック抽選</a>""",
        DETAIL: HTML,
    }
    calls = []

    class Fetcher:
        def fetch(self, url, etag=None, last_modified=None):
            calls.append(url)
            return FetchResult(url, 200, pages[url], {})

    config = replace(
        CONFIG,
        sources=[SOURCE],
        system={
            **CONFIG.system,
            "minimum_host_interval_seconds": 0,
            "max_parallel_hosts": 1,
        },
    )
    state = MonitorState.load(tmp_path / "state.json")
    cases, _, alerts = run_pipeline(config, monitor_state=state, http_fetcher=Fetcher())
    assert calls == [INDEX, DETAIL]
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "rakuten_books"
    assert cases[0].start_at == datetime(2026, 8, 27, 10, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert cases[0].end_at == datetime(2026, 8, 30, 23, 59, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert state.data["monitors"][SOURCE.id]["routes"][INDEX]["discovered_urls"] == [DETAIL]


@freeze_time("2026-09-05 21:00:00+09:00")
def test_rakuten_expired_lottery_is_verified_but_not_emitted():
    diagnostics = {}
    cases, _, alerts = parse_retailer_lottery_detail(
        HTML,
        DETAIL,
        SOURCE,
        CONFIG,
        diagnostics=diagnostics,
    )
    assert not cases
    assert not alerts
    assert diagnostics == {
        "validated_product": 1,
        "validated_application_period": 1,
        "application_ended": 1,
    }


@freeze_time("2026-08-27 12:00:00+09:00")
def test_rakuten_deck_does_not_borrow_box_from_footer():
    html = HTML.replace("拡張パック 30th CELEBRATION", "30th CELEBRATION プレミアムデッキセット")
    cases, _, _ = parse_retailer_lottery_detail(
        html + "<footer>拡張パック1BOX</footer>", DETAIL, SOURCE, CONFIG
    )
    assert not cases


def test_rakuten_purchase_date_is_not_used_when_application_date_missing():
    html = HTML.replace(
        "抽選受付期間：2026/08/27(木) 10:00 〜 2026/08/30(日) 23:59", "受付期間は未定"
    )
    cases, _, alerts = parse_retailer_lottery_detail(html, DETAIL, SOURCE, CONFIG)
    assert not cases
    assert [alert.reason_code for alert in alerts] == ["retailer_application_period_missing"]
