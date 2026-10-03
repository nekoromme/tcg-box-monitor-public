from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date, datetime
from pathlib import Path

from freezegun import freeze_time

from tcg_monitor.config import load_config
from tcg_monitor.models import SourceTier
from tcg_monitor.parsers.generic import parse_generic
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.parsers.premium_bandai import parse_nyuka_now_lottery_summary
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState

CONFIG = load_config("sites.yaml")
SOURCES = {source.id: source for source in CONFIG.sources}
FIXTURES = Path(__file__).parent / "fixtures"
OFFICIAL_URL = "https://limited.yodobashi.com/entry/shared/"
START = datetime.fromisoformat("2026-10-05T11:00:00+09:00")
END = datetime.fromisoformat("2026-10-06T10:59:00+09:00")


def official_case():
    cases, _, alerts = parse_generic(
        (FIXTURES / "yodobashi_30th_cardset_20261002.html").read_text(),
        OFFICIAL_URL, SOURCES["yodobashi"], CONFIG,
    )
    assert not alerts
    assert len(cases) == 1
    return cases[0]


def pokeget_cases():
    source = SOURCES["secondary_pokeget_news"]
    return parse_yahoo_realtime(
        (FIXTURES / "pokeget_lottery_20261003.html").read_text(),
        source.discovery_urls[0], source, CONFIG, date(2026, 10, 3),
    )


@freeze_time("2026-10-03T02:32:00Z")
def test_real_official_page_keeps_separate_product_and_period_blocks_together() -> None:
    case = official_case()
    assert SOURCES["yodobashi"].enabled
    assert SOURCES["yodobashi"].discovery_urls == [OFFICIAL_URL]
    assert case.canonical_product_key == "pokemon_30th_cardset"
    assert case.start_at == START
    assert case.end_at == END
    assert case.source_tier == SourceTier.OFFICIAL


@freeze_time("2026-10-03T02:32:00Z")
def test_real_pokeget_feed_routes_announcements_and_ignores_roundups_and_results() -> None:
    cases, releases, alerts = pokeget_cases()
    assert not releases and not alerts
    assert {case.retailer_id for case in cases} == {"yodobashi", "edion_online"}
    assert len(cases) == 2
    case = next(case for case in cases if case.retailer_id == "yodobashi")
    assert case.start_at == START
    assert case.end_at == END
    assert case.official_url == OFFICIAL_URL
    assert case.source_url == "https://x.com/PokeGetInfoMain/status/2105901122766643439"
    assert case.source_tier == SourceTier.SECONDARY


@freeze_time("2026-10-03T02:32:00Z")
def test_summary_and_social_paths_dedupe_with_official_and_keep_delivery(tmp_path: Path) -> None:
    # 入荷Nowの実際の表記を使用。別店舗欄の日時は流用しない。
    html = """
    <h2>近日受付開始予定のストア</h2>
    <h3>ヨドバシ・ドット・コム</h3><table>
    <tr><th>対象商品</th><td>ポケモンカード 30th CELEBRATION カードセット各種</td></tr>
    <tr><th>開始日</th><td>10月5日(月)11:00</td></tr>
    <tr><th>終了日</th><td>10月6日(火)10:59</td></tr>
    <tr><th>応募ページ</th><td><a href="https://limited.yodobashi.com/entry/shared/">
    ヨドバシ・ドット・コムの応募ページ</a></td></tr></table>
    <h3>ほかの店舗</h3><p>開始日10月9日(金)10:00</p>
    """
    summary, _, alerts = parse_nyuka_now_lottery_summary(
        html, "https://nyuka-now.com/archives/2459",
        SOURCES["nyuka_now_fullcomp_livepocket"], CONFIG,
    )
    assert not alerts and len(summary) == 1
    secondary = next(case for case in pokeget_cases()[0] if case.retailer_id == "yodobashi")
    merged, alerts = merge_lotteries([secondary, *summary, official_case()])
    assert not alerts and len(merged) == 1
    assert merged[0].source_tier == SourceTier.OFFICIAL
    assert merged[0].start_at == START
    assert merged[0].end_at == END

    # ポケゲトで先に通知した後に公式が復旧しても、配信履歴を引き継ぐ。
    old = merge_lotteries([secondary])[0][0]
    state = MonitorState.load(tmp_path / "state.json")
    state.data["seen_cases"][old.case_id] = asdict(old)
    state.mark_delivered(f"lottery:scheduled:{old.case_id}")
    state.migrate_case_identity(merged[0])
    assert state.delivered(f"lottery:scheduled:{merged[0].case_id}")


@freeze_time("2026-10-03T02:32:00Z")
def test_shared_yodobashi_url_does_not_suppress_next_months_same_box(tmp_path: Path) -> None:
    # 同じ固定URLは再販でも使い回す。カードセットだけでなく通常BOXも区別する。
    old = replace(
        official_case(), canonical_product_key="test_box", product_name="拡張パック「テスト」",
        product_category="拡張パック", case_id="",
    ).with_id()
    new = replace(old, start_at=datetime.fromisoformat("2026-11-05T11:00:00+09:00"),
                  end_at=None, case_id="").with_id()
    assert old.case_id != new.case_id
    state = MonitorState.load(tmp_path / "state.json")
    state.data["seen_cases"][old.case_id] = asdict(old)
    state.mark_delivered(f"lottery:scheduled:{old.case_id}")
    assert state.migrate_case_identity(new) is None
    assert not state.delivered(f"lottery:scheduled:{new.case_id}")


@freeze_time("2026-10-07T02:32:00Z")
def test_closed_official_cardset_is_not_reintroduced() -> None:
    cases, _, alerts = parse_generic(
        (FIXTURES / "yodobashi_30th_cardset_20261002.html").read_text(),
        OFFICIAL_URL, SOURCES["yodobashi"], CONFIG,
    )
    assert not cases and not alerts


def test_pokeget_account_must_match_and_unknown_or_multistore_posts_are_ignored() -> None:
    source = SOURCES["secondary_pokeget_news"]
    template = (
        '<div class="Tweet_TweetContainer__test"><p>{body}</p>'
        '<a href="https://x.com/{account}/status/2105901122766643439">投稿</a></div>'
    )
    common = ' ポケカ「30th CELEBRATION カードセット」抽選販売 受付期間10/5 11:00～10/6 10:59'
    for account, body in (
        ("other_account", "ヨドバシ" + common),
        ("PokeGetInfoMain", "ヨドバシ・コジマ" + common),
        ("PokeGetInfoMain", "対象外店舗" + common),
        ("PokeGetInfoMain", "ヨドバシ ポケカ 抽選販売 受付期間10/6まで"),
    ):
        cases, _, _ = parse_yahoo_realtime(
            template.format(account=account, body=body), source.discovery_urls[0],
            source, CONFIG, date(2026, 10, 3),
        )
        assert not cases
