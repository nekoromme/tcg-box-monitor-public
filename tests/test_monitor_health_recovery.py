from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from freezegun import freeze_time

import tcg_monitor.ocr as ocr
from tcg_monitor.config import load_config
from tcg_monitor.fetching import FetchProblem, PageFetcher
from tcg_monitor.fxembed import X_EPOCH_MS, FxEmbedReader, post_markup, timeline_url
from tcg_monitor.http_client import FetchResult, HttpFetcher
from tcg_monitor.parsers.local_lottery import _application_deadline, parse_yahoo_realtime
from tcg_monitor.parsers.snkrdunk import parse_snkrdunk

CONFIG = load_config("sites.yaml")


class SequenceFetcher(HttpFetcher):
    def __init__(self, responses: list[tuple[int, str]]) -> None:
        super().__init__(minimum_host_interval=0)
        self.responses = responses
        self.calls: list[str] = []

    def fetch(self, url: str, etag: str | None = None,
              last_modified: str | None = None) -> FetchResult:
        self.calls.append(url)
        status, body = self.responses.pop(0)
        return FetchResult(url, status, body, {})


@freeze_time("2026-10-05T04:00:00Z")
@pytest.mark.parametrize("failed", [(404, '{"code":404,"results":[]}'),
                                    (502, "upstream error"),
                                    (200, '{"code":200,"error":"upstream","results":[]}')])
def test_temporary_provider_failure_recovers_without_missing_range(failed) -> None:
    source = next(s for s in CONFIG.sources if s.id == "secondary_pokeget_news")
    root = timeline_url(source)
    assert root
    fetcher = SequenceFetcher([failed, (200, '{"code":200,"results":[]}')])
    reader = FxEmbedReader(PageFetcher(fetcher, lambda *args: ""), {})
    reader.fetch(root, source)
    assert fetcher.calls == [root, root]
    assert reader.reports[root]["complete"] is True


def test_provider_rate_limit_is_not_retried_or_bypassed() -> None:
    source = next(s for s in CONFIG.sources if s.id == "secondary_pokeget_news")
    root = timeline_url(source)
    assert root
    fetcher = SequenceFetcher([(429, "rate limited")])
    reader = FxEmbedReader(PageFetcher(fetcher, lambda *args: pytest.fail("browser")), {})
    with pytest.raises(FetchProblem):
        reader.fetch(root, source)
    assert fetcher.calls == [root]


@freeze_time("2026-10-11T04:00:00Z")
def test_busy_initial_timeline_reaches_old_boundary_before_advancing_watermark() -> None:
    from datetime import UTC, datetime

    source = next(s for s in CONFIG.sources if s.id == "secondary_pokeget_news")
    root = timeline_url(source)
    assert root
    responses = []
    for page in range(7):
        day = 10 if page < 6 else 1
        sid = (int(datetime(2026, 10, day, tzinfo=UTC).timestamp()) * 1000 - X_EPOCH_MS) << 22
        rows = [{"id": str(sid + (6 - page) * 100 + i), "text": "平常営業中",
                 "author": {"screen_name": "PokeGetInfoMain"}} for i in range(20)]
        responses.append((200, json.dumps({"code": 200, "results": rows,
                                          "cursor": {"bottom": f"page-{page + 1}"}})))
    fetcher = SequenceFetcher(responses)
    marks = {}
    reader = FxEmbedReader(PageFetcher(fetcher, lambda *args: ""), marks,
                          max_pages=CONFIG.system["fxembed_max_pages"])
    reader.fetch(root, source)
    assert len(fetcher.calls) == 7
    assert reader.reports[root]["posts"] == 120
    assert reader.reports[root]["complete"] is True
    assert marks["pokegetinfomain"]


@freeze_time("2026-10-05T04:00:00Z")
def test_actual_closed_lottery_notices_do_not_raise_missing_product_alerts() -> None:
    posts = json.loads(Path("tests/fixtures/health_closed_posts_20261005.json").read_text())
    for post in posts:
        account = post["author"]["screen_name"]
        source = next(s for s in CONFIG.sources if s.parser_options.get("account") == account)
        html = post_markup(post, account.lower())
        assert html
        diagnostics: dict[str, int] = {}
        cases, _, alerts = parse_yahoo_realtime(
            html, "https://x.com/" + account, source, CONFIG, diagnostics=diagnostics,
        )
        assert not cases and not alerts
        assert diagnostics["application_ended"] == 1


def test_unread_current_lottery_still_raises_an_alert() -> None:
    source = next(s for s in CONFIG.sources if s.id == "yahoo_realtime_batoloco_morioka")
    html = ('<article><p>ポケカ 新弾の抽選申込は本日締切です！</p>'
            '<a href="https://x.com/batoloco_mrok/status/2098951672383111615">投稿</a></article>')
    with freeze_time("2026-09-13T04:00:00Z"):
        cases, _, alerts = parse_yahoo_realtime(html, "https://x.com/", source, CONFIG)
    assert not cases
    assert [a.reason_code for a in alerts] == ["yahoo_lottery_post_without_product"]


def test_historical_draw_days_do_not_override_a_new_application_period() -> None:
    text = ("9/19・9/20の2日間は店頭抽選販売を実施しました。"
            "新たな抽選の応募期間：10/5〜10/8。当選発表10/12。")
    assert _application_deadline(text, date(2026, 10, 5)) == date(2026, 10, 8)


def test_snkrdunk_detail_link_row_is_part_of_its_parent_campaign() -> None:
    source = next(s for s in CONFIG.sources if s.id == "snkrdunk_pokemon")
    html = """<h1>【ポケカ】30th CELEBRATIONの予約・抽選情報</h1>
    <p>拡張パック「30th CELEBRATION」 発売日 2026年9月16日</p>
    <h4>文真堂書店ゲオ 倉賀野店</h4><table>
    <tr><th>抽選期間</th><td>10/3〜10/7</td></tr>
    <tr><th>当選発表</th><td>10/12</td></tr>
    <tr><th>抽選詳細</th><td><a href="https://x.com/buntckuraga_jp/status/2106174748661289247">
    X：文真堂書店ゲオ 倉賀野店（@buntckuraga_jp）</a></td></tr></table>"""
    cases, _, alerts = parse_snkrdunk(html, "https://snkrdunk.com/articles/32998/", source, CONFIG)
    assert len(cases) == 1
    assert not alerts


def test_exact_x_attachment_default_size_recovers_a_missing_original(monkeypatch) -> None:
    original = "https://pbs.twimg.com/media/HTwRr98agAAxsbl.png?name=orig"
    default = original.split("?")[0]
    calls = []

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, **kwargs):
            calls.append(url)
            return SimpleNamespace(status_code=404 if url == original else 200,
                                   headers={"content-type": "image/png"},
                                   content=b"image", raise_for_status=lambda: None)

    monkeypatch.setattr(ocr.httpx, "Client", lambda **kwargs: Client())
    monkeypatch.setattr(ocr.shutil, "which", lambda name: "tesseract")
    monkeypatch.setattr(ocr.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout="対象カード", stderr=""))
    assert ocr.read_image_text([original]) == "対象カード"
    assert calls == [original, default]
