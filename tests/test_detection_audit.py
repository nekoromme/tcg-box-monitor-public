"""Offline evidence of wiring, distinct from live source/candidate evidence."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from freezegun import freeze_time

from tcg_monitor.config import load_config
from tcg_monitor.http_client import FetchResult
from tcg_monitor.models import GameSupport, SourceTier
from tcg_monitor.parsers.local_lottery import parse_yahoo_realtime
from tcg_monitor.parsers.pokemon_center import is_pokemon_center_news_index
from tcg_monitor.pipeline import SourceMetrics, _healthy_fallbacks, run_pipeline
from tcg_monitor.social_discovery import social_discovery_urls
from tcg_monitor.state import MonitorState

CONFIG = load_config("sites.yaml")
OFFICIAL_SOCIAL = [
    source
    for source in CONFIG.sources
    if source.enabled
    and source.parser_kind == "yahoo_realtime"
    and source.source_tier != SourceTier.SECONDARY
]


class Fetcher:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def fetch(self, url, etag=None, last_modified=None):
        self.calls.append((url, etag, last_modified))
        return FetchResult(url, 200, self.pages[url], {})


def config_for(source):
    return replace(
        CONFIG,
        sources=[source],
        system={
            **CONFIG.system,
            "minimum_host_interval_seconds": 0,
            "max_parallel_hosts": 1,
            "request_timeout_seconds": 1,
        },
    )


@pytest.mark.parametrize("source", OFFICIAL_SOCIAL, ids=lambda source: source.id)
def test_every_enabled_official_account_has_unfiltered_same_account_search(source):
    urls = social_discovery_urls(source)
    matches = [
        url
        for url in urls
        if urlsplit(url).netloc == "search.yahoo.co.jp"
        and parse_qs(urlsplit(url).query).get("p") == [f"id:{source.parser_options['account']}"]
    ]
    assert len(matches) == 1
    assert set(source.discovery_urls) <= set(urls)
    # Reapplying cannot grow the URL list each polling cycle.
    assert social_discovery_urls(replace(source, discovery_urls=urls)) == urls


def test_secondary_search_scope_is_not_widened():
    for source in CONFIG.sources:
        if source.source_tier == SourceTier.SECONDARY:
            assert social_discovery_urls(source) == source.discovery_urls


@freeze_time("2026-09-05 21:00:00+09:00")
def test_production_account_search_recovers_candidate_and_records_route(tmp_path):
    source = next(s for s in OFFICIAL_SOCIAL if s.id == "yahoo_realtime_batoloco_fukushima")
    source = replace(source, discovery_urls=source.discovery_urls[:1])
    first, account_url = social_discovery_urls(source)
    body = """<div class="Tweet_TweetContainer__test"><p>
    ポケモンカードゲーム 拡張パック「30th CELEBRATION」1BOX 抽選販売
    応募期間：9月5日10:00～9月10日23:59</p>
    <a href="https://x.com/batoloco_fuku/status/2095742710691053657">投稿</a></div>"""
    fetcher = Fetcher({first: "<main>一致する情報は見つかりませんでした</main>", account_url: body})
    state = MonitorState.load(tmp_path / "state.json")
    cases, _, alerts = run_pipeline(config_for(source), monitor_state=state, http_fetcher=fetcher)
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "batoloco_fukushima"
    record = state.data["monitors"][source.id]
    assert record["routes"][first]["status"] == "parsed_empty"
    assert record["routes"][account_url]["parsed_count"] == 1
    assert record["routes"][account_url]["diagnostics"]["account_posts"] == 1
    assert set(record["route_evidence"]) == {account_url}
    state.record_monitor(
        source.id, {"parsed_count": 0}, success=True, recorded_at=datetime.now(UTC)
    )
    assert state.data["monitors"][source.id]["candidate_runs"] == 1
    assert state.data["monitors"][source.id]["last_candidate_at"]
    assert set(state.data["monitors"][source.id]["route_evidence"]) == {account_url}


@pytest.mark.parametrize(
    "source_id,index,detail",
    [
        (
            "pokemon_center_online",
            "https://www.pokemoncenter-online.com/news/",
            "https://www.pokemoncenter-online.com/news/?id=20260905",
        ),
        (
            "pokemon_center_store",
            "https://shop.pokemon.co.jp/ja/shop/common/news/",
            "https://shop.pokemon.co.jp/ja/shop/common/news/202609/000393.html",
        ),
    ],
)
def test_pokemon_center_index_to_detail_reparses_with_legacy_etag(
    tmp_path, source_id, index, detail
):
    source = replace(next(s for s in CONFIG.sources if s.id == source_id), discovery_urls=[index])
    assert is_pokemon_center_news_index(source_id, index)
    assert not is_pokemon_center_news_index(source_id, detail)
    fetcher = Fetcher(
        {
            index: f'<a href="{detail}">ポケモンカードゲーム 抽選販売</a>',
            detail: """
    <h1>ポケモンカードゲーム 抽選販売</h1><p>公開日：2026年9月5日</p>
    <p>拡張パック「30th CELEBRATION」1BOX</p>
    <p>応募期間：2026年9月5日10:00～9月10日23:59</p>""",
        }
    )
    state = MonitorState.load(tmp_path / "state.json")
    state.data["http_cache"] = {index: {"etag": '"unchanged"'}}
    cases, _, alerts = run_pipeline(config_for(source), monitor_state=state, http_fetcher=fetcher)
    assert not alerts
    assert len(cases) == 1
    assert cases[0].source_url == detail
    assert fetcher.calls == [(index, None, None), (detail, None, None)]
    assert state.data["monitors"][source_id]["routes"][index]["discovered_urls"] == [detail]


@pytest.mark.parametrize(
    "fallback_retailer,game,covered",
    [
        (None, "pokemon_card", False),
        ("another_shop", "pokemon_card", False),
        ("target", "one_piece_card", False),
        ("target", "pokemon_card", True),
    ],
)
def test_fallback_needs_candidate_for_same_retailer_and_game(fallback_retailer, game, covered):
    original = OFFICIAL_SOCIAL[0]
    primary = replace(
        original,
        id="target",
        fallback_source_ids=["backup"],
        parser_options={"retailer_id": "target"},
        supported_games={"pokemon_card": GameSupport.VERIFIED},
    )
    backup = replace(primary, id="backup", fallback_source_ids=[])
    metrics = SourceMetrics("backup")
    if fallback_retailer:
        metrics.retailer_ids.add(fallback_retailer)
        metrics.retailer_game_ids.add((fallback_retailer, game))
    config = replace(CONFIG, sources=[primary, backup])
    result = _healthy_fallbacks(
        config, {"target": False, "backup": True}, evidence={"backup": metrics}
    )
    assert bool(result) == covered


@pytest.mark.parametrize("host", ["publish.twitter.com", "publish.x.com"])
@pytest.mark.parametrize("strict,wrong_account", [(False, False), (True, False), (False, True)])
def test_mixed_post_selects_box_after_deck_and_preserves_strict_filter(host, strict, wrong_account):
    source = next(s for s in OFFICIAL_SOCIAL if s.id == "yahoo_realtime_tsutaya_akebono")
    source = replace(
        source, parser_options={**source.parser_options, "strict_product_exclusions": strict}
    )
    account = "different_shop" if wrong_account else source.parser_options["account"]
    status = f"https://x.com/{account}/status/2095742710691053657"
    payload = json.dumps(
        {
            "url": status,
            "author_url": f"https://x.com/{account}",
            "html": f"""
    <blockquote class="twitter-tweet"><p>ポケモンカードゲーム 抽選販売受付
    「プレミアムスターターデッキ」および拡張パック「30th CELEBRATION」1BOX
    応募期間：9月5日10:00～9月10日23:59</p><a href="{status}">投稿</a></blockquote>""",
        }
    )
    if wrong_account:
        with pytest.raises(ValueError):
            parse_yahoo_realtime(
                payload, f"https://{host}/oembed", source, CONFIG, detected_on=date(2026, 9, 5)
            )
    else:
        cases, _, _ = parse_yahoo_realtime(
            payload, f"https://{host}/oembed", source, CONFIG, detected_on=date(2026, 9, 5)
        )
        assert len(cases) == (0 if strict else 1)
        if cases:
            assert "30th CELEBRATION" in cases[0].product_name
            assert "デッキ" not in cases[0].product_name
