from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from tcg_monitor.cli import _prepare_cases, _summary_markdown
from tcg_monitor.config import load_config
from tcg_monitor.http_client import FetchResult
from tcg_monitor.models import LotteryCase, OpportunityKind, SourceTier
from tcg_monitor.parsers.premium_bandai import parse_nyuka_now_lottery_summary
from tcg_monitor.parsers.snkrdunk import parse_snkrdunk
from tcg_monitor.pipeline import run_pipeline
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState

CONFIG = load_config("sites.yaml")
SOURCES = {source.id: source for source in CONFIG.sources}


def _secondary_case() -> LotteryCase:
    return LotteryCase(
        "one_piece_card", "hmv", "HMV", "Heroines Edition vol.2【EB-05】",
        "BOX", "EB-05", date(2026, 10, 1), "https://livepocket.jp/e/hmv-draw",
        "https://snkrdunk.com/articles/32599/", SourceTier.SECONDARY, "test", "medium",
    ).with_id()


@pytest.mark.parametrize("official_already_seen", [False, True])
def test_secondary_then_official_keeps_delivery_across_runs(
    tmp_path: Path, official_already_seen: bool,
) -> None:
    secondary = _secondary_case()
    official = replace(
        secondary, start_at=datetime(2026, 10, 1, 12, tzinfo=ZoneInfo("Asia/Tokyo")),
        official_url="https://t.co/official-application",
        source_url="https://x.com/HMV_Japan/status/2105067964882198698",
        source_tier=SourceTier.OFFICIAL_INDIRECT, case_id="",
    ).with_id()
    state = MonitorState.load(tmp_path / "state.json")
    state.data["seen_cases"][secondary.case_id] = {
        **asdict(secondary), "start_at": secondary.start_at.isoformat(),
    }
    state.mark_delivered(f"lottery:started:{secondary.case_id}")
    state.data["calendar_sync"][f"lottery:{secondary.case_id}"] = {"event_id": "same-event"}
    if official_already_seen:
        state.data["seen_cases"][official.case_id] = {
            **asdict(official), "start_at": official.start_at.isoformat(),
        }
    prepared, new_count = _prepare_cases(state, [official])
    assert new_count == 0
    assert prepared[0].case_id == official.case_id
    assert state.delivered(f"lottery:started:{official.case_id}")
    assert state.calendar_case_identity(official.case_id) == secondary.case_id
    assert state.data["calendar_sync"][f"lottery:{official.case_id}"]["event_id"] == "same-event"
    assert set(state.data["seen_cases"]) == {official.case_id}
    merged, alerts = merge_lotteries([secondary, official])
    assert merged == [official]
    assert not alerts


@pytest.mark.parametrize("change", ["next_draw", "other_store", "other_product", "sale"])
def test_distinct_campaigns_do_not_inherit_another_notification(
    tmp_path: Path, change: str,
) -> None:
    old = _secondary_case()
    changes = {
        "next_draw": {"start_at": date(2026, 11, 1)},
        "other_store": {"retailer_id": "fullcomp"},
        "other_product": {"product_name": "EGGHEAD CRISIS【EB-04】",
                          "canonical_product_key": "EB-04"},
        "sale": {"opportunity_kind": OpportunityKind.DIRECT_SALE},
    }
    current = replace(
        old, **changes[change], official_url="https://livepocket.jp/e/new-draw",
        source_url="https://x.com/HMV_Japan/status/2205067964882198698", case_id="",
    ).with_id()
    state = MonitorState.load(tmp_path / "state.json")
    state.data["seen_cases"][old.case_id] = {**asdict(old), "start_at": old.start_at.isoformat()}
    state.mark_delivered(f"lottery:started:{old.case_id}")
    assert _prepare_cases(state, [current])[1] == 1
    assert not state.delivered(f"lottery:started:{current.case_id}")


def test_shared_kids_guide_does_not_suppress_next_month_draw(tmp_path: Path) -> None:
    old = replace(
        _secondary_case(), retailer_id="kids_republic",
        official_url="https://www.kidsrepublic.jp/campaign",
        source_url="https://nyuka-now.com/archives/97393", case_id="",
    ).with_id()
    current = replace(old, start_at=date(2026, 11, 1), case_id="").with_id()
    assert current.case_id != old.case_id
    state = MonitorState.load(tmp_path / "state.json")
    state.data["seen_cases"][old.case_id] = {**asdict(old), "start_at": old.start_at.isoformat()}
    state.mark_delivered(f"lottery:started:{old.case_id}")
    assert _prepare_cases(state, [current])[1] == 1
    assert not state.delivered(f"lottery:started:{current.case_id}")


@pytest.mark.parametrize(
    ("game_id", "summary_title", "official_title"),
    [
        ("pokemon_card", "ポケモンカード ストームエメラルダ 1BOX",
         "拡張パック「ストームエメラルダ」"),
        ("yu_gi_oh", "遊戯王OCG デュエルモンスターズ カオス・オリジンズ 1BOX",
         "基本パック「カオス・オリジンズ」"),
        ("lorcana", "ディズニー・ロルカナ・TCG 日本語版 逆襲のアースラ 1BOX",
         "ブースターパック「逆襲のアースラ」"),
        ("gundam_card", "ガンダムカードゲーム ブースターパック Newtype Rising 1BOX",
         "ブースターパック「Newtype Rising」"),
    ],
)
def test_game_prefix_and_box_wording_do_not_create_second_notification(
    tmp_path: Path, game_id: str, summary_title: str, official_title: str,
) -> None:
    old = replace(_secondary_case(), game_id=game_id, retailer_id="kids_republic",
                  product_name=summary_title, canonical_product_key=summary_title,
                  case_id="").with_id()
    current = replace(old, product_name=official_title, canonical_product_key=official_title,
                      official_url="https://t.co/new-official-link",
                      source_url="https://x.com/kidsrepublicjp/status/2105067964882198698",
                      source_tier=SourceTier.OFFICIAL_INDIRECT, case_id="").with_id()
    state = MonitorState.load(tmp_path / "state.json")
    state.data["seen_cases"][old.case_id] = {**asdict(old), "start_at": old.start_at.isoformat()}
    state.mark_delivered(f"lottery:started:{old.case_id}")
    assert _prepare_cases(state, [current])[1] == 0
    assert state.delivered(f"lottery:started:{current.case_id}")
    merged, alerts = merge_lotteries([old, current])
    assert merged == [current] and not alerts


@pytest.mark.parametrize(
    ("game_id", "summary_id", "product"),
    [
        ("pokemon_card", 2459, "ポケモンカード 拡張パック「ストームエメラルダ」1BOX"),
        ("one_piece_card", 97393,
         "ONE PIECEカードゲーム エクストラブースター Heroines Edition vol.2【EB-05】1BOX"),
        ("yu_gi_oh", 72605, "遊戯王OCG デュエルモンスターズ カオス・オリジンズ 1BOX"),
        ("dragon_ball_fusion_world", 141863,
         "ドラゴンボールスーパーカードゲーム フュージョンワールド 限界を超えし者【FB04】1BOX"),
    ],
)
def test_kids_supplement_reads_game_specific_active_table(
    game_id: str, summary_id: int, product: str,
) -> None:
    def block(scope: str) -> str:
        return f"""
        <h2>{scope}</h2><h3>キッズリパブリック</h3><table>
          <tr><th>対象商品</th><td>{product}</td></tr>
          <tr><th>開始日</th><td>2026年10月1日(木)11:00</td></tr>
          <tr><th>終了日</th><td>2026年10月3日(土)19:59</td></tr>
        </table><a href="https://www.kidsrepublic.jp/campaign">公式案内</a>
        """

    source = SOURCES["nyuka_now_fullcomp_livepocket"]
    url = f"https://nyuka-now.com/archives/{summary_id}"
    cases, _, alerts = parse_nyuka_now_lottery_summary(
        block("抽選・予約応募受付中のストア") + block("応募受付終了（過去の抽選）"),
        url, source, CONFIG,
    )
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "kids_republic"
    assert cases[0].game_id == game_id
    assert cases[0].end_at == datetime(2026, 10, 3, 19, 59, tzinfo=ZoneInfo("Asia/Tokyo"))
    closed, _, closed_alerts = parse_nyuka_now_lottery_summary(
        block("応募受付終了（過去の抽選）"), url, source, CONFIG,
    )
    assert not closed and not closed_alerts


def test_fullcomp_closed_block_is_not_reintroduced_by_supplement() -> None:
    html = """
    <h2>応募受付終了（過去の抽選）</h2><h3>フルコンプ 一部店舗</h3>
    <table><tr><th>対象商品</th><td>ポケモンカード 拡張パック「ストームエメラルダ」1BOX</td></tr>
    <tr><th>開始日</th><td>2026年9月1日</td></tr></table>
    <a href="https://livepocket.jp/e/old-draw">応募先</a>
    """
    cases, _, alerts = parse_nyuka_now_lottery_summary(
        html, "https://nyuka-now.com/archives/2459",
        SOURCES["nyuka_now_fullcomp_livepocket"], CONFIG,
    )
    assert not cases and not alerts


def test_dragonball_summary_does_not_use_onepiece_only_bandai_parser() -> None:
    html = """
    <h2>抽選・予約応募受付中のストア</h2><h3>プレミアムバンダイ</h3>
    <table><tr><th>対象商品</th><td>ドラゴンボール フュージョンワールド FB04 1BOX</td></tr>
    <tr><th>開始日</th><td>2026年10月1日</td></tr></table>
    """
    cases, _, alerts = parse_nyuka_now_lottery_summary(
        html, "https://nyuka-now.com/archives/141863",
        SOURCES["nyuka_now_fullcomp_livepocket"], CONFIG,
    )
    assert not cases and not alerts


@pytest.mark.parametrize("source_id", ["snkrdunk_pokemon", "snkrdunk_onepiece"])
def test_hmv_and_ministop_rows_are_no_longer_ignored(source_id: str) -> None:
    html = Path(f"tests/fixtures/{source_id}.html").read_text()
    html += """
    <table>
      <tr><td>HMVトレカショップ</td><td>抽選期間：2026年10月1日12:00〜10月3日23:59</td>
      <td><a href="https://livepocket.jp/e/hmv-draw">応募</a></td></tr>
      <tr><td>ミニストップオンライン</td><td>抽選期間：2026年10月1日12:00〜10月3日23:59</td>
      <td><a href="https://online.ministop.co.jp/">応募</a></td></tr>
    </table>
    """
    cases, _, _ = parse_snkrdunk(html, "https://snkrdunk.com/articles/32599/",
                               SOURCES[source_id], CONFIG)
    assert {"hmv", "ministop_online"} <= {case.retailer_id for case in cases}


class _OfficialPostFetcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch(self, url: str, **_kwargs: str | None) -> FetchResult:
        self.calls.append(url)
        assert urlsplit(url).netloc == "search.yahoo.co.jp"
        html = """
        <title>Yahoo!リアルタイム検索</title><div class="Tweet_TweetContainer__test">
        <p>ポケカ 拡張パック「ストームエメラルダ」1BOX 抽選販売
        応募期間：10月1日(木)12:00～10月3日(土)23:59
        <a href="https://livepocket.jp/e/official-draw">応募ページ</a></p>
        <a href="https://x.com/hbst_event/status/2105067964882198698">投稿</a></div>
        """
        return FetchResult(url, 200, html, {})


@freeze_time("2026-10-01 03:00:00")
def test_livepocket_link_in_official_post_is_not_fetched(tmp_path: Path) -> None:
    fetcher = _OfficialPostFetcher()
    config = replace(CONFIG, sources=[SOURCES["yahoo_realtime_hobby_station_official"]])
    state = MonitorState.load(tmp_path / "state.json")
    cases, _, alerts = run_pipeline(config, http_fetcher=fetcher, monitor_state=state)
    assert not alerts
    assert len(cases) == 1
    assert cases[0].official_url == "https://livepocket.jp/e/official-draw"
    assert len(fetcher.calls) == 2
    assert state.data["last_run_summary"]["monitored_source_ids"] == [
        "yahoo_realtime_hobby_station_official",
    ]
    assert all(
        "livepocket.jp" not in url and "twstalker.com" not in url
        for source in CONFIG.sources if source.enabled for url in source.discovery_urls
    )


def test_current_summary_excludes_stopped_parent_history(tmp_path: Path) -> None:
    state = MonitorState.load(tmp_path / "state.json")
    state.data["last_run_summary"] = {"monitored_source_ids": ["current_official"]}
    state.data["monitors"] = {
        "current_official": {"outcome": "successful"},
        "stopped_parent": {"outcome": "failed"},
    }
    summary = _summary_markdown(state)
    assert "current_official" in summary and "stopped_parent" not in summary
    assert "stopped_parent" in state.data["monitors"]
