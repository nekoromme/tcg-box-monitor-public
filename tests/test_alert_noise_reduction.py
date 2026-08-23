from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from tcg_monitor.cli import _deliver_alerts
from tcg_monitor.config import load_config
from tcg_monitor.models import Alert
from tcg_monitor.parsers.generic import parse_generic, parse_onepiece_topics
from tcg_monitor.parsers.snkrdunk import parse_snkrdunk
from tcg_monitor.state import MonitorState


def _source(source_id: str):  # type: ignore[no-untyped-def]
    config = load_config("sites.yaml")
    source = next(item for item in config.sources if item.id == source_id)
    return config, source


def test_geo_valid_product_period_suppresses_partial_block_alert() -> None:
    config, source = _source("geo")
    html = """
    <title>ゲオ抽選販売</title>
    <div>
      <h1>8月22日発売 ONE PIECEカードゲーム
      ブースターパック「世界最強の戦士」抽選販売</h1>
    </div>
    <div>
      ONE PIECEカードゲーム ブースターパック「世界最強の戦士」
      応募期間 8/3(月) 11:00 ～ 8/6(木) 17:59
    </div>
    """

    cases, _, alerts = parse_generic(
        html,
        "https://geo-online.co.jp/news/775",
        source,
        config,
    )

    assert len(cases) == 1
    assert not alerts


def test_onepiece_topics_uses_only_explicit_start_entries() -> None:
    config, source = _source("onepiece_official_topics")
    html = """
    <h1>TOPICS</h1>
    <a href="/products/op17.html">
      ブースターパック「世界最強の戦士」8月22日発売決定！
      PRODUCTS 2026.03.19
    </a>
    <a href="https://p-bandai.jp/item/item-1000999999/">
      「ブースターパック 神の島の冒険【OP-15】」
      本日プレミアムバンダイ抽選販売の受付を開始！
      OTHER 2026.07.24
    </a>
    """

    cases, _, alerts = parse_onepiece_topics(
        html,
        "https://www.onepiece-cardgame.com/topics/",
        source,
        config,
    )

    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "premium_bandai"
    assert cases[0].start_at == date(2026, 7, 24)


def test_snkrdunk_uses_update_date_for_amazon_but_ignores_pending_placeholders() -> None:
    config, source = _source("snkrdunk_onepiece")
    html = """
    <h1>【ワンピースカード】世界最強の戦士の予約・抽選情報【7/24更新】</h1>
    <p>2026年7月24日 更新</p>
    <ul>
      <li>「世界最強の戦士」の発売日はいつ？</li>
      <li>「世界最強の戦士」の予約・抽選情報【7/24更新】</li>
    </ul>
    <p>ブースターパック「世界最強の戦士」が、
    2026年8月22日(土)に発売されることが決定。</p>
    <table>
      <tr><td><a href="https://www.amazon.co.jp/dp/B0TESTOP17">Amazon</a></td>
      <td>- 招待リクエスト</td></tr>
      <tr><td>ポケモンセンターオンライン</td><td>- 受付前</td></tr>
    </table>
    <h4>ポケモンセンターオンライン</h4>
    <p>抽選期間- 判明次第更新</p>
    <p>商品名 ブースターパック「世界最強の戦士」</p>
    <p>発売日 2026年8月22日(土)</p>
    """

    cases, releases, alerts = parse_snkrdunk(
        html,
        "https://snkrdunk.com/articles/32599/",
        source,
        config,
    )

    assert [item.release_date for item in releases] == [date(2026, 8, 22)]
    assert len(cases) == 1
    assert cases[0].retailer_id == "amazon_jp"
    assert cases[0].start_at == date(2026, 7, 24)
    assert cases[0].official_url == "https://www.amazon.co.jp/dp/B0TESTOP17"
    assert cases[0].extraction_method == "snkrdunk_open_invitation_seen"
    assert not alerts


def test_snkrdunk_does_not_combine_related_article_category_with_body_quote() -> None:
    config, source = _source("snkrdunk_pokemon")
    html = """
    <aside>
      <a>関連記事 ハイクラスパック「別の商品」</a>
    </aside>
    <article>
      <h1>【ポケカ】ストームエメラルダの予約・抽選情報まとめ【7/30更新】</h1>
      <p>2026年7月30日 更新</p>
      <p>ポケカより、2026年7月31日に、
      拡張パック「ストームエメラルダ」が発売される。</p>
      <p>『ポケットモンスター ルビー・サファイア』で登場した
      伝説のポケモンを収録。</p>
      <h2>商品情報</h2>
      <p>商品名 | 拡張パック「ストームエメラルダ」</p>
      <p>発売日 | 2026年7月31日</p>
    </article>
    """

    cases, releases, alerts = parse_snkrdunk(
        html,
        "https://snkrdunk.com/articles/32581/",
        source,
        config,
    )

    assert not cases
    assert not alerts
    assert len(releases) == 1
    assert releases[0].product_name == "拡張パック「ストームエメラルダ」"
    assert releases[0].product_category == "拡張パック"


def test_snkrdunk_resale_article_parses_hobby_search_official_lottery() -> None:
    config, source = _source("snkrdunk_pokemon")
    html = """
    <article>
      <h1>【ポケカ】ストームエメラルダの再販はいつ？再販入荷情報まとめ【8/12更新】</h1>
      <p>2026年8月12日 更新</p>
      <h2>商品情報</h2>
      <p>商品名 | 拡張パック「ストームエメラルダ」</p>
      <p>発売日 | 2026年7月31日</p>
      <h4>ホビーサーチ</h4>
      <p>抽選期間 | 8/12 18:00〜8/15</p>
      <p><a href="https://www.1999.co.jp/11341851">抽選受付ページ</a></p>
    </article>
    """

    cases, releases, alerts = parse_snkrdunk(
        html,
        "https://snkrdunk.com/articles/32892/",
        source,
        config,
    )

    assert not alerts
    assert len(releases) == 1
    assert len(cases) == 1
    assert cases[0].retailer_id == "hobby_search"
    assert cases[0].start_at == datetime(2026, 8, 12, 18, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    assert cases[0].official_url == "https://www.1999.co.jp/11341851"


def test_snkrdunk_matches_heading_alias_to_product_table_title() -> None:
    config, source = _source("snkrdunk_pokemon")
    html = """
    <aside>
      <a>関連記事 ハイクラスパック「FUR(フューチャリスティックレア)」</a>
    </aside>
    <article>
      <h1>【ポケカ】30th CELEBRATION(30th セレブレーション)の予約・抽選情報</h1>
      <p>2026年7月27日 更新</p>
      <p>ポケカ30周年を記念した拡張パック「30th CELEBRATION」を発売。</p>
      <h2>商品情報</h2>
      <p>商品名 | 拡張パック「30th CELEBRATION」</p>
      <p>発売日 | 2026年9月16日</p>
      <table><tr><td>Amazon</td><td>- 招待リクエスト</td></tr></table>
    </article>
    """

    cases, releases, alerts = parse_snkrdunk(
        html,
        "https://snkrdunk.com/articles/32425/",
        source,
        config,
    )

    assert not alerts
    assert len(releases) == 1
    assert releases[0].product_name == "拡張パック「30th CELEBRATION」"
    assert len(cases) == 1
    assert cases[0].product_name == "拡張パック「30th CELEBRATION」"


def test_snkrdunk_release_date_is_scoped_to_product_section() -> None:
    """Unrelated footer cards must never become the monitored BOX release date."""

    config, source = _source("snkrdunk_pokemon")
    html = """
    <article>
      <h1>【ポケカ】30th CELEBRATION(30th セレブレーション)の予約・抽選情報</h1>
      <p>ポケカ30周年を記念した
      拡張パック「30th CELEBRATION」を発売。</p>

      <h2>「30th CELEBRATION」の発売日はいつ？</h2>
      <p><strong>2026年9月16日(水)</strong><span>に世界同時発売となる。</span></p>

      <h2>商品情報</h2>
      <table>
        <tr><th>商品名</th><td>拡張パック「30th CELEBRATION」</td></tr>
        <tr><th>発売日</th><td>2026年9月16日(水)</td></tr>
      </table>

      <h2>関連記事</h2>
      <a href="/articles/unrelated">8/22発売予定｜別ジャンルの商品</a>
    </article>
    """

    _, releases, alerts = parse_snkrdunk(
        html,
        "https://snkrdunk.com/articles/32425/",
        source,
        config,
    )

    assert not alerts
    assert len(releases) == 1
    assert releases[0].release_date == date(2026, 9, 16)


class _DiscordSpy:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def send(self, title: str, description: str) -> dict[str, str]:
        self.messages.append((title, description))
        return {"status": "sent"}


def _alert(name: str, reason: str = "lottery_text_without_start") -> Alert:
    return Alert(
        None,
        name,
        f"https://example.com/{name}",
        name,
        [],
        reason,
        "テスト異常",
        None,
        f"https://example.com/{name}",
    ).with_fingerprint()


def _state(path: Path) -> MonitorState:
    return MonitorState(path)


def test_multiple_alerts_are_sent_as_one_digest(tmp_path: Path) -> None:
    spy = _DiscordSpy()
    state = _state(tmp_path / "state.json")
    now = datetime(2026, 7, 24, 21, 0, tzinfo=ZoneInfo("Asia/Tokyo"))

    _deliver_alerts(state, spy, [_alert("a"), _alert("b")], now, 24)

    assert len(spy.messages) == 1
    assert spy.messages[0][0] == "【監視異常まとめ】2件"
    assert "1. a" in spy.messages[0][1]
    assert "2. b" in spy.messages[0][1]


def test_transport_alert_reminder_is_weekly(tmp_path: Path) -> None:
    spy = _DiscordSpy()
    state = _state(tmp_path / "state.json")
    alert = _alert("blocked-source", "repeated_http_error")
    now = datetime(2026, 7, 24, 6, 0, tzinfo=ZoneInfo("Asia/Tokyo"))

    _deliver_alerts(state, spy, [alert], now, 24)
    assert not spy.messages
    assert state.data["alerts"][alert.fingerprint]["consecutive_runs"] == 1

    _deliver_alerts(state, spy, [alert], now + timedelta(hours=12), 24)
    assert len(spy.messages) == 1
    assert state.data["alerts"][alert.fingerprint]["consecutive_runs"] == 2

    _deliver_alerts(state, spy, [alert], now + timedelta(days=8), 24)
    assert len(spy.messages) == 2
    description = spy.messages[0][1]
    assert "repeated_http_error" not in description
    assert "通信・ページ取得の障害" in description
    assert "2026/07/24 18:00" in description


def test_active_alert_is_not_repeated_when_reminders_are_disabled(
    tmp_path: Path,
) -> None:
    spy = _DiscordSpy()
    state = _state(tmp_path / "state.json")
    alert = _alert("static-problem")
    now = datetime(2026, 7, 24, 6, 0, tzinfo=ZoneInfo("Asia/Tokyo"))

    _deliver_alerts(state, spy, [alert], now, 0)
    _deliver_alerts(state, spy, [alert], now + timedelta(days=30), 0)

    assert len(spy.messages) == 1
    assert state.data["alerts"][alert.fingerprint]["status"] == "active"


def test_partial_run_does_not_resolve_an_unrelated_active_alert(
    tmp_path: Path,
) -> None:
    spy = _DiscordSpy()
    state = _state(tmp_path / "state.json")
    alert = _alert("source-a")
    now = datetime(2026, 7, 24, 6, 0, tzinfo=ZoneInfo("Asia/Tokyo"))

    _deliver_alerts(state, spy, [alert], now, 0)
    _deliver_alerts(
        state,
        spy,
        [],
        now + timedelta(hours=12),
        0,
        {"source-b"},
    )
    _deliver_alerts(state, spy, [alert], now + timedelta(days=2), 0)

    assert len(spy.messages) == 1
    assert state.data["alerts"][alert.fingerprint]["status"] == "active"


def test_one_missing_run_does_not_reopen_the_same_incident(tmp_path: Path) -> None:
    spy = _DiscordSpy()
    state = _state(tmp_path / "state.json")
    alert = _alert("flaky-feed")
    now = datetime(2026, 7, 24, 6, 0, tzinfo=ZoneInfo("Asia/Tokyo"))

    _deliver_alerts(state, spy, [alert], now, 0)
    _deliver_alerts(state, spy, [], now + timedelta(hours=12), 0)
    assert state.data["alerts"][alert.fingerprint]["status"] == "active"
    assert state.data["alerts"][alert.fingerprint]["missing_runs"] == 1

    _deliver_alerts(state, spy, [alert], now + timedelta(days=1), 0)

    assert len(spy.messages) == 1
    assert state.data["alerts"][alert.fingerprint]["missing_runs"] == 0


def test_resolved_incident_is_notified_when_it_really_recurs(tmp_path: Path) -> None:
    spy = _DiscordSpy()
    state = _state(tmp_path / "state.json")
    alert = _alert("recovered-source")
    now = datetime(2026, 7, 24, 6, 0, tzinfo=ZoneInfo("Asia/Tokyo"))

    _deliver_alerts(state, spy, [alert], now, 0)
    _deliver_alerts(state, spy, [], now + timedelta(hours=12), 0)
    _deliver_alerts(state, spy, [], now + timedelta(days=1), 0)
    assert state.data["alerts"][alert.fingerprint]["status"] == "resolved"

    _deliver_alerts(state, spy, [alert], now + timedelta(days=2), 0)

    assert len(spy.messages) == 2
    assert state.data["alerts"][alert.fingerprint]["status"] == "active"


def test_alert_summary_change_reuses_active_incident(tmp_path: Path) -> None:
    spy = _DiscordSpy()
    state = _state(tmp_path / "state.json")
    now = datetime(2026, 7, 24, 6, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    first = Alert(
        None,
        "ocr-source",
        "https://example.com/status/123",
        "画像内の応募開始日時を確認できません",
        [],
        "yahoo_image_ocr_repeated_failure",
        "OCR解析に連続2回失敗しました",
        None,
        "https://example.com/status/123",
    ).with_fingerprint()
    updated = Alert(
        None,
        "ocr-source",
        "https://example.com/status/123",
        "画像内の応募開始日時を確認できません",
        [],
        "yahoo_image_ocr_repeated_failure",
        "OCR解析に連続3回失敗しました",
        None,
        "https://example.com/status/123",
    ).with_fingerprint()
    assert first.fingerprint == updated.fingerprint

    _deliver_alerts(state, spy, [first], now, 24)
    _deliver_alerts(state, spy, [updated], now + timedelta(hours=1), 24)

    assert len(spy.messages) == 1
    assert list(state.data["alerts"]) == [first.fingerprint]
    assert state.data["alerts"][first.fingerprint]["status"] == "active"
