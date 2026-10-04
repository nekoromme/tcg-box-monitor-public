from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

import pytest
from freezegun import freeze_time

from tcg_monitor.cli import _prepare_cases
from tcg_monitor.config import load_config
from tcg_monitor.fetching import PageFetcher
from tcg_monitor.fxembed import X_EPOCH_MS, FxEmbedReader, post_markup, timeline_url
from tcg_monitor.http_client import FetchResult, HttpFetcher
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.pipeline import run_pipeline
from tcg_monitor.state import MonitorState

CONFIG = load_config("sites.yaml")
SOURCE = next(s for s in CONFIG.sources if s.id == "secondary_pokeget_news")
ROOT = timeline_url(SOURCE)
assert ROOT is not None
FIXTURE = Path("tests/fixtures/fxembed_pokeget_20261004.json").read_text()


class Responses(HttpFetcher):
    def __init__(self, pages: dict[str, str | tuple[int, str]]) -> None:
        super().__init__(minimum_host_interval=0)
        self.pages = pages
        self.calls: list[str] = []

    def fetch(self, url: str, etag: str | None = None,
              last_modified: str | None = None) -> FetchResult:
        self.calls.append(url)
        assert etag is None and last_modified is None
        page = self.pages[url]
        status, body = page if isinstance(page, tuple) else (200, page)
        return FetchResult(url, status, body, {})


def post(day: int, text: str = "告知") -> dict[str, object]:
    sid = (int(datetime(2026, 10, day, tzinfo=UTC).timestamp()) * 1000 - X_EPOCH_MS) << 22
    return {"id": str(sid), "text": text, "author": {"screen_name": "PokeGetInfoMain"}}


def page(rows: list[dict[str, object]], cursor: str | None = None) -> str:
    return json.dumps({"code": 200, "results": rows, "cursor": {"bottom": cursor}})


@freeze_time("2026-10-04T12:00:00Z")
def test_public_snapshot_does_not_include_quote_or_repost_and_keeps_images() -> None:
    payload = json.loads(FIXTURE)
    p = payload["results"][1]
    p["quote"] = post(3, "無関係なFUTURISTIC BOX抽選")
    markup = post_markup(p, "pokegetinfomain")
    assert markup is not None
    assert "FUTURISTIC" not in markup
    assert 'src="https://pbs.twimg.com/media/' in markup
    assert "profile_images" not in markup
    p["author"]["screen_name"] = "some_other_shop"
    assert post_markup(p, "pokegetinfomain") is None


@freeze_time("2026-10-04T12:00:00Z")
def test_api_is_read_even_when_yahoo_returned_a_different_valid_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("tcg_monitor.pipeline.read_image_text", lambda urls: "")
    yahoo = '<article><p>平常営業中</p><a href="https://x.com/PokeGetInfoMain/status/'
    yahoo += str(post(4)["id"]) + '">投稿</a></article>'
    fetcher = Responses({**dict.fromkeys(SOURCE.discovery_urls, yahoo), ROOT: FIXTURE})
    config = replace(CONFIG, sources=[SOURCE], system={**CONFIG.system, "max_parallel_hosts": 1})
    state = MonitorState.load(tmp_path / "state.json")
    cases, _, alerts = run_pipeline(config, monitor_state=state, http_fetcher=fetcher)
    assert ROOT in fetcher.calls
    assert any(c.retailer_id == "yodobashi" and c.canonical_product_key == "pokemon_30th_cardset"
               for c in cases)
    assert not alerts
    assert state.data["monitors"][SOURCE.id]["routes"][ROOT]["provider"] == "fxembed"


@freeze_time("2026-10-04T12:00:00Z")
def test_existing_delivery_and_calendar_identity_are_reused(tmp_path: Path) -> None:
    raw = json.loads(FIXTURE)
    markup = "".join(post_markup(p, "pokegetinfomain") or "" for p in raw["results"])
    current = parse_yahoo_realtime(markup, ROOT, SOURCE, CONFIG)[0]
    assert current
    state = MonitorState.load(tmp_path / "state.json")
    for case in current:
        # 本番と同じ元投稿URL・抽選回を、旧経路の通知済みとして保存する。
        state.data["seen_cases"][case.case_id] = asdict(case)
        state.mark_delivered(f"lottery:started:{case.case_id}")
        state.data["calendar_sync"][case.case_id] = {"event_id": "existing-event"}
    for _ in range(2):
        prepared, count = _prepare_cases(state, current)
        assert count == 0
        assert all(state.delivered(f"lottery:started:{c.case_id}") for c in prepared)
    assert len(state.data["calendar_sync"]) == len(current)


@freeze_time("2026-10-04T12:00:00Z")
def test_pagination_does_not_stop_at_old_pinned_post_and_caches_account() -> None:
    first = page([post(1), post(4), post(3)], "next +/=")
    second_url = ROOT + "&" + urlencode({"cursor": "next +/="})
    fetcher = Responses({ROOT: first, second_url: page([post(2)])})
    marks = {"pokegetinfomain": str(post(2)["id"])}
    reader = FxEmbedReader(
        PageFetcher(fetcher, lambda *args: pytest.fail("browser must not run")), marks,
    )
    result = reader.fetch(ROOT, SOURCE)
    assert len(fetcher.calls) == 2
    assert str(post(2)["id"]) in result.html
    assert reader.reports[ROOT]["complete"] is True
    assert marks["pokegetinfomain"] == post(4)["id"]
    assert reader.fetch(ROOT, replace(SOURCE, id="same_account_other_game")) == result
    assert len(fetcher.calls) == 2


@freeze_time("2026-10-04T12:00:00Z")
@pytest.mark.parametrize("failure", [(404, "not found"), (200, '{"code":404}'),
                                   (200, '{"code":200,"results":[],"error":"upstream"}')])
def test_partial_page_is_reported_and_watermark_does_not_advance(
    failure: tuple[int, str],
) -> None:
    fetcher = Responses({ROOT: page([post(4)], "next"), ROOT + "&cursor=next": failure})
    marks = {"pokegetinfomain": str(post(2)["id"])}
    reader = FxEmbedReader(
        PageFetcher(fetcher, lambda *args: pytest.fail("browser must not run")), marks,
    )
    result = reader.fetch(ROOT, SOURCE)
    assert str(post(4)["id"]) in result.html
    assert reader.reports[ROOT]["complete"] is False
    assert reader.reports[ROOT]["incomplete_reason"]
    assert marks["pokegetinfomain"] == post(2)["id"]


@freeze_time("2026-10-04T12:00:00Z")
def test_page_limit_is_not_claimed_as_complete() -> None:
    reader = FxEmbedReader(
        PageFetcher(Responses({ROOT: page([post(4)], "next")}), lambda *args: ""),
        {}, max_pages=1,
    )
    reader.fetch(ROOT, SOURCE)
    assert reader.reports[ROOT]["incomplete_reason"] == "page_limit"
    assert not reader.watermarks


@freeze_time("2026-10-04T12:00:00Z")
def test_provider_image_caches_do_not_invalidate_each_other(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads: list[list[str]] = []

    def ocr(urls: list[str]) -> str:
        reads.append(urls)
        return "応募受付期間：10月2日〜10月9日"

    monkeypatch.setattr("tcg_monitor.pipeline.read_image_text", ocr)
    payload = json.loads(FIXTURE)
    # Same actual post, different provider image URLs: both results stay cached.
    markup = "".join(post_markup(p, "pokegetinfomain") or "" for p in payload["results"])
    yahoo = markup.replace("https://pbs.twimg.com/media/", "https://rts-pctr.c.yimg.jp/")
    fetcher = Responses({**dict.fromkeys(SOURCE.discovery_urls, yahoo), ROOT: FIXTURE})
    config = replace(CONFIG, sources=[SOURCE], system={**CONFIG.system, "max_parallel_hosts": 1})
    state = MonitorState.load(tmp_path / "state.json")
    run_pipeline(config, monitor_state=state, http_fetcher=fetcher,
                 ocr_cache=state.data["ocr_cache"])
    first_count = len(reads)
    assert first_count > 0
    assert state.data["ocr_cache"] and state.data["fxembed_ocr_cache"]
    run_pipeline(config, monitor_state=state, http_fetcher=fetcher,
                 ocr_cache=state.data["ocr_cache"])
    assert len(reads) == first_count


@freeze_time("2026-10-04T12:00:00Z")
@pytest.mark.parametrize("game_id,item", [
    (game_id, item)
    for game_id, game in CONFIG.games.items()
    for item in game.additional_products
    if item.enabled and not item.name_patterns
], ids=lambda item: getattr(item, "id", item))
def test_every_selected_nonbox_product_survives_public_x_parser(game_id, item) -> None:
    source = next(s for s in CONFIG.sources if s.id == "yahoo_realtime_tsutaya_ichinoseki_store")
    body = (f"{CONFIG.games[game_id].name} {item.name} 抽選販売のお知らせ。"
            "応募受付期間：2026年10月4日10時〜10月6日23時59分。WEBでお申し込みください。")
    raw = post(4, body)
    raw["author"] = {"screen_name": source.parser_options["account"]}
    html = post_markup(raw, str(source.parser_options["account"]).lower())
    assert html is not None
    found = parse_yahoo_realtime(html, timeline_url(source), source, CONFIG)[0]
    assert any(c.canonical_product_key.split(":")[0] == item.id for c in found)


@freeze_time("2026-10-04T12:00:00Z")
def test_first_image_failure_keeps_range_for_retry_then_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = next(s for s in CONFIG.sources
                    if s.id == "yahoo_realtime_torecano_mizusawa")
    source = replace(original, discovery_urls=original.discovery_urls[:1],
                     fallback_on_empty_result=False)
    root = timeline_url(source)
    assert root is not None
    raw = post(4, "お知らせ。画像をご確認ください。")
    raw["author"] = {"screen_name": source.parser_options["account"]}
    raw["media"] = {"photos": [{"url": "https://pbs.twimg.com/media/notice.jpg"}]}
    quiet = "<main>一致する情報は見つかりませんでした</main>"
    fetcher = Responses({source.discovery_urls[0]: quiet, root: page([raw])})
    config = replace(CONFIG, sources=[source], system={
        **CONFIG.system, "max_parallel_hosts": 1, "social_account_fallback": False,
    })
    state = MonitorState.load(tmp_path / "state.json")

    def failed_ocr(_urls):
        raise RuntimeError("temporary image failure")

    monkeypatch.setattr("tcg_monitor.pipeline.read_image_text", failed_ocr)
    run_pipeline(config, monitor_state=state, http_fetcher=fetcher)
    assert state.data["ocr_pending"]  # first failure does not yet emit a repeated-failure alert
    assert not state.data["fxembed_watermarks"]
    monkeypatch.setattr("tcg_monitor.pipeline.read_image_text", lambda urls:
                        "ポケモンカード 30th CELEBRATION カードセット 抽選販売 "
                        "応募受付期間：10月4日10時〜10月6日23時59分")
    cases, _, _ = run_pipeline(config, monitor_state=state, http_fetcher=fetcher)
    assert any(c.canonical_product_key == "pokemon_30th_cardset" for c in cases)
    assert not state.data["ocr_pending"]
    assert state.data["fxembed_watermarks"]


@freeze_time("2026-10-04T12:00:00Z")
def test_link_to_an_earlier_post_does_not_assign_current_body_to_its_id() -> None:
    raw = json.loads(FIXTURE)["results"][1]
    old_url = "https://x.com/PokeGetInfoMain/status/2104000000000000000"
    raw.setdefault("raw_text", {}).setdefault("facets", []).append(
        {"type": "url", "replacement": old_url},
    )
    html = post_markup(raw, "pokegetinfomain")
    assert html is not None and f'href="{old_url}"' not in html
    found = parse_yahoo_realtime(html, ROOT, SOURCE, CONFIG)[0]
    assert found and all(str(raw["id"]) in c.source_url for c in found)


@freeze_time("2026-10-04T12:00:00Z")
def test_rp_giveaway_is_not_a_product_lottery_or_parser_failure() -> None:
    source = next(s for s in CONFIG.sources if s.id == "yahoo_realtime_dragonstar_online")
    raw = post(4, "シングル販売スタート記念 RPキャンペーン 応募受付中 "
               "イジンデン 千怪戦戯 それぞれ2名様に抽選でプレゼント")
    raw["author"] = {"screen_name": source.parser_options["account"]}
    html = post_markup(raw, str(source.parser_options["account"]).lower())
    assert html is not None
    diagnostics = {}
    cases, _, alerts = parse_yahoo_realtime(
        html, timeline_url(source), source, CONFIG, diagnostics=diagnostics,
    )
    assert not cases and not alerts
    assert diagnostics["disallowed_application"] == 1
