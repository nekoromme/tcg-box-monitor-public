from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
from freezegun import freeze_time

from tcg_monitor import cli
from tcg_monitor.config import load_config
from tcg_monitor.models import SourceTier
from tcg_monitor.parsers.retailer_release_calendar import (
    discover_clabo_calendar_urls,
    parse_clabo_release_calendar,
)
from tcg_monitor.source_priority import merge_releases
from tcg_monitor.state import MonitorState

URL = "https://www.c-labo.jp/special/2028/"


def document(day="11月21日(土)発売", stamp="2026.09.01", name="神の支配【OP-18】"):
    # 日付は検証用の仮値。実際の掲載内容を主張するものではない。
    return f"""<article><h1>TCG発売日カレンダー</h1><p class="article_date">{stamp}</p>
    <div><h3>{day}</h3><table><thead><tr>
    <th>カテゴリ</th><th>商品名</th><th>価格(税込)</th></tr></thead><tbody>
    <tr><td>ワンピース</td><td>ONE PIECEカードゲーム ブースターパック {name}</td>
    <td>240円</td></tr>
    <tr><td>ワンピース</td><td>オフィシャルカードスリーブ【OP-18】</td><td>880円</td></tr>
    <tr><td>遊戯王RD</td><td>ブースターパック その他</td><td>198円</td></tr>
    </tbody></table></div></article>"""


def parse(html):
    config = load_config("sites.yaml")
    source = next(s for s in config.sources if s.id == "clabo_release_calendar")
    return parse_clabo_release_calendar(html, URL, source, config)


@freeze_time("2026-09-19")
def retailer():
    _, releases, alerts = parse(document())
    assert not alerts
    assert len(releases) == 1
    return releases[0]


def test_discovery_follows_calendar_link_after_article_number_changes():
    assert discover_clabo_calendar_urls(
        """
      <a href="/special/9999/">発売日カレンダー</a>
      <a href="https://unrelated.example/special/1/">発売日カレンダー</a>
      <a href="/special/123/">抽選</a>""",
        "https://www.c-labo.jp/",
    ) == ["https://www.c-labo.jp/special/9999/"]


@freeze_time("2026-09-19")
@pytest.mark.parametrize(
    "day,stamp",
    [
        ("11月21日(日)発売", "2026.09.01"),
        ("11月発売", "2026.09.01"),
        ("11月31日(土)発売", "2026.09.01"),
        ("11月21日(土)発売", "2025.09.01"),
        ("11月21日(土)発売", "2026.09.31"),
        ("11月21日(土)発売", "2026.10.01"),
    ],
)
def test_uncertain_or_stale_dates_do_not_create_releases(day, stamp):
    _, releases, alerts = parse(document(day, stamp))
    assert not releases
    assert alerts


@freeze_time("2026-12-20")
def test_rollover_uses_article_year_and_checks_weekday():
    _, releases, alerts = parse(document("1月2日(土)発売", "2026.12.01"))
    assert not alerts
    assert releases[0].release_date == date(2027, 1, 2)


@freeze_time("2026-09-19")
def test_update_mid_month_does_not_reject_earlier_rows():
    _, releases, alerts = parse(document("9月5日(土)発売", "2026.09.15"))
    assert not alerts
    assert releases[0].release_date == date(2026, 9, 5)


def test_official_month_gets_trusted_exact_date_and_official_day_wins():
    store = retailer()
    official = replace(
        store,
        product_name="別表記 OP-18",
        source_tier=SourceTier.OFFICIAL,
        release_date=None,
        release_month="2026-11",
        source_url="https://official/",
    )
    merged, alerts = merge_releases([official, store])
    assert merged == [store]
    assert not alerts
    official = replace(official, release_date=date(2026, 11, 28), release_month=None)
    merged, alerts = merge_releases([store, official])
    assert merged == [official]
    assert alerts  # 食い違いは黙って捨てず、既存の障害通知経路に残す。
    merged, alerts = merge_releases(
        [store, replace(official, release_date=None, release_month="2026-12")]
    )
    assert merged[0].source_tier == SourceTier.OFFICIAL
    assert alerts


def test_unapproved_pages_and_methods_remain_rejected(tmp_path):
    store = retailer()
    state = MonitorState.load(tmp_path / "state.json")
    for untrusted in [
        replace(store, source_url="https://other.example/special/2028/"),
        replace(store, extraction_method="generic"),
        replace(store, release_date=None, release_month="2026-11"),
    ]:
        assert cli._prepare_releases(state, [untrusted]) == ([], 0)
    assert cli._prepare_releases(state, [store])[0] == [store]


def test_saved_official_day_is_preserved_when_manufacturer_crawl_fails(tmp_path):
    store = retailer()
    state = MonitorState.load(tmp_path / "state.json")
    official = replace(
        store,
        source_tier=SourceTier.OFFICIAL,
        release_date=date(2026, 11, 28),
        official_url="https://official/",
    )
    state.data["seen_releases"][official.release_id] = official.__dict__
    prepared, count = cli._prepare_releases(state, [store])
    assert count == 0
    assert prepared[0].release_date == official.release_date
    assert prepared[0].source_tier == SourceTier.OFFICIAL


def test_retailer_then_official_updates_same_calendar_event(tmp_path, monkeypatch):
    store = retailer()
    values = [store]
    calls, messages = [], []

    class Calendar:
        def reconcile(self, kind, internal_id, summary, when, description, **kwargs):
            calls.append((internal_id, when, description))
            return {"status": "updated", "event_id": "same-event"}

    class Discord:
        def send(self, title, description):
            messages.append((title, description))
            return {"status": "sent"}

    monkeypatch.setattr(cli, "run_pipeline", lambda *a, **kw: ([], values, []))
    monkeypatch.setattr(cli, "CalendarAdapter", Calendar)
    monkeypatch.setattr(cli, "DiscordAdapter", Discord)
    path = tmp_path / "state.json"
    state = MonitorState.load(path)
    state.mark_baseline()
    state.arm()
    with freeze_time("2026-09-19"):
        cli.main(["--state", str(path), "run"])
        cli.main(["--state", str(path), "run"])
        assert len(messages) == 1
        assert "カードラボ" in messages[0][1]
        assert "公式ページ:" not in messages[0][1]
        assert "カードラボ" in calls[0][2]
        values[:] = [
            replace(
                store,
                source_tier=SourceTier.OFFICIAL,
                product_name="別表記 OP-18",
                release_date=date(2026, 11, 28),
                official_url="https://official/",
            )
        ]
        cli.main(["--state", str(path), "run"])
    assert {call[0] for call in calls} == {store.release_id}
    assert calls[-1][1] == date(2026, 11, 28)
    assert "公式商品ページ:" in calls[-1][2]
    assert len(messages) == 2


@freeze_time("2026-09-19")
@pytest.mark.parametrize(
    "category,store_name,official_name",
    [
        (
            "ポケモン",
            "ポケモンカードゲーム MEGA 拡張パック 30th CELEBRATION",
            "拡張パック「30th CELEBRATION」",
        ),
        ("遊戯王", "遊☆戯☆王 ORIGINAL ARTWORK COLLECTION", "ORIGINAL ARTWORK COLLECTION"),
    ],
)
def test_retailer_prefixes_do_not_duplicate_official_products(category, store_name, official_name):
    html = document().replace("<td>ワンピース</td>", f"<td>{category}</td>")
    html = html.replace("ONE PIECEカードゲーム ブースターパック 神の支配【OP-18】", store_name)
    _, releases, _ = parse(html)
    assert len(releases) == 1
    official = replace(
        releases[0],
        product_name=official_name,
        source_tier=SourceTier.OFFICIAL,
        canonical_product_key="official-slug",
    ).with_id()
    merged, _ = merge_releases([releases[0], official])
    assert merged == [official]
