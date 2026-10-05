from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from freezegun import freeze_time

from tcg_monitor.config import load_config
from tcg_monitor.fetching import FetchProblem, PageFetcher
from tcg_monitor.fxembed import FxEmbedReader, post_markup, timeline_url
from tcg_monitor.http_client import FetchResult, HttpFetcher
from tcg_monitor.ocr import ExpiredImageProxyError
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.pipeline import run_pipeline
from tcg_monitor.state import MonitorState

CONFIG = load_config("sites.yaml")
SOURCE = next(s for s in CONFIG.sources if s.id == "yahoo_realtime_dmm_tsuhan")
POST = json.loads(Path("tests/fixtures/dmm_expired_proxy_post_20260907.json").read_text())
API = "https://api.fxtwitter.com/status/" + POST["id"]
PROXY = "https://rts-pctr.c.yimg.jp/expired-dmm"


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


def reader_for(payload: dict) -> tuple[FxEmbedReader, SequenceFetcher]:
    fetcher = SequenceFetcher([(200, json.dumps(payload))])
    reader = FxEmbedReader(PageFetcher(fetcher, lambda *args: pytest.fail("browser")),
                           {"dmm_tsuhan": "2106926534179340691"})
    return reader, fetcher


def test_exact_old_post_media_does_not_mix_quotes_or_move_timeline_progress() -> None:
    post = {**POST, "quote": {"media": {"photos": [{"url": "https://pbs.twimg.com/quote"}]}}}
    reader, fetcher = reader_for({"code": 200, "tweet": post})
    before = dict(reader.watermarks)
    expected = [p["url"] for p in POST["media"]["photos"]]
    assert reader.post_image_urls(POST["url"], SOURCE) == expected
    assert reader.post_image_urls(POST["url"], SOURCE) == expected
    assert fetcher.calls == [API]
    assert reader.watermarks == before


@pytest.mark.parametrize("mutation", ["author", "id"])
def test_mismatched_post_identity_is_not_used(mutation) -> None:
    post = {**POST, **({"author": {"screen_name": "another"}} if mutation == "author"
                      else {"id": "1234"})}
    reader, _ = reader_for({"code": 200, "tweet": post})
    with pytest.raises(ValueError, match="identity"):
        reader.post_image_urls(POST["url"], SOURCE)


def test_unrelated_post_url_is_rejected_before_fetch() -> None:
    reader, fetcher = reader_for({})
    with pytest.raises(ValueError, match="configured account"):
        reader.post_image_urls("https://x.com/another/status/" + POST["id"], SOURCE)
    assert not fetcher.calls


@pytest.mark.parametrize("code", [403, 429])
def test_embedded_access_limit_is_not_retried(code) -> None:
    reader, fetcher = reader_for({"code": code})
    with pytest.raises(FetchProblem) as problem:
        reader.post_image_urls(POST["url"], SOURCE)
    assert problem.value.blocked and fetcher.calls == [API]


def expired_markup() -> str:
    markup = post_markup(POST, "dmm_tsuhan")
    assert markup
    return markup.replace(POST["media"]["photos"][0]["url"], PROXY)


@freeze_time("2026-10-05T05:00:00Z")
@pytest.mark.parametrize("image_has_lottery", [False, True])
def test_expired_toy_post_is_read_before_deciding_whether_it_contains_tcg(image_has_lottery):
    pending: dict[str, object] = {POST["url"]: {"attempts": 1}}
    diagnostics: dict[str, int] = {}
    image_text = ("ポケモンカードゲーム 拡張パック「30th CELEBRATION」"
                  "抽選受付期間：9/8〜10/8") if image_has_lottery else "ガンプラ プラモデル"

    def expired(urls):
        raise ExpiredImageProxyError("HTTP 400")

    cases, _, alerts = parse_yahoo_realtime(
        expired_markup(), POST["url"], SOURCE, CONFIG, known_releases=[],
        ocr_reader=expired, expired_proxy_reader=lambda url: image_text,
        ocr_pending=pending, diagnostics=diagnostics,
    )
    assert len(cases) == int(image_has_lottery)
    assert not alerts and not pending
    assert diagnostics["expired_proxy_recovered"] == 1


@freeze_time("2026-10-05T05:00:00Z")
def test_failed_same_post_fallback_keeps_the_real_ocr_incident():
    pending: dict[str, object] = {POST["url"]: {"attempts": 1}}

    def expired(urls):
        raise ExpiredImageProxyError("HTTP 400")

    def blocked(url):
        raise FetchProblem(API, "http_status_403", status_code=403, blocked=True)

    cases, _, alerts = parse_yahoo_realtime(
        expired_markup(), POST["url"], SOURCE, CONFIG, known_releases=[],
        ocr_reader=expired, expired_proxy_reader=blocked, ocr_pending=pending,
    )
    assert not cases and pending
    assert [a.reason_code for a in alerts] == ["yahoo_image_ocr_repeated_failure"]


@freeze_time("2026-10-05T05:00:00Z")
def test_live_pipeline_recovers_exact_old_post_outside_the_timeline_lookback(tmp_path, monkeypatch):
    import tcg_monitor.pipeline as pipeline

    root = timeline_url(SOURCE)
    assert root
    responses = [(200, expired_markup()),
                 (200, json.dumps({"code": 200, "tweet": POST})),
                 (200, expired_markup()),
                 (200, '{"code":200,"results":[]}')]
    fetcher = SequenceFetcher(responses)
    calls = []

    def read_images(urls):
        calls.append(urls)
        if urls == [PROXY]:
            raise ExpiredImageProxyError("HTTP 400")
        return "ガンプラ プラモデル"

    monkeypatch.setattr(pipeline, "read_image_text", read_images)
    config = replace(CONFIG, sources=[SOURCE],
                     system={**CONFIG.system, "max_parallel_hosts": 1})
    state = MonitorState.load(tmp_path / "state.json")
    state.data["ocr_pending"] = {POST["url"]: {"attempts": 1}}
    cases, _, alerts = run_pipeline(config, monitor_state=state, http_fetcher=fetcher,
                                   ocr_cache=state.data.setdefault("ocr_cache", {}))
    assert not cases and not alerts and not state.data["ocr_pending"]
    assert fetcher.calls == [SOURCE.discovery_urls[0], API, SOURCE.discovery_urls[1], root]
    assert calls == [[PROXY], [POST["media"]["photos"][0]["url"]]]
