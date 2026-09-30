from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from freezegun import freeze_time

from tcg_monitor.browser_fetch import pokemon_release_window_url
from tcg_monitor.config import load_config
from tcg_monitor.http_client import FetchResult
from tcg_monitor.parsers.pokemon_official_products import (
    discover_pokemon_product_api_pages,
    parse_pokemon_official_products,
)
from tcg_monitor.pipeline import run_pipeline
from tcg_monitor.state import MonitorState

API_URL = "https://www.pokemon-card.com/products/resultAPI.php?productType=expansion"


def _payload(products: list[dict[str, str]]) -> str:
    return json.dumps({
        "result": 1, "errMsg": "", "thisPage": int(bool(products)),
        "maxPage": int(bool(products)), "hitCnt": len(products), "products": products,
    })


def test_official_product_api_preserves_title_type_date_and_official_link() -> None:
    config = load_config("sites.yaml")
    source = next(s for s in config.sources if s.id == "pokemon_official_products")
    payload = _payload([{
        "productTitle": "拡張パック「30th CELEBRATION」", "productType": "拡張パック",
        "releaseDate": "2026年 9月16日（水）",
        "link_detailPage": "https://www.30th.pokemon-card.com/product/m6a",
    }])
    cases, releases, alerts = parse_pokemon_official_products(payload, API_URL, source, config)
    assert not cases and not alerts
    assert len(releases) == 1
    assert releases[0].release_date == date(2026, 9, 16)
    assert releases[0].product_name == "拡張パック「30th CELEBRATION」"
    assert releases[0].official_url == "https://www.30th.pokemon-card.com/product/m6a"


@pytest.mark.parametrize("payload", [
    '<main>メンテナンス中です</main>',
    '{"result":0,"errMsg":"error","products":[]}',
    '{"result":1,"errMsg":"","products":[]}',
    '{"result":1,"errMsg":"","products":[],"hitCnt":1,"thisPage":1,"maxPage":1}',
])
def test_invalid_api_results_are_not_healthy_empty_searches(payload: str) -> None:
    config = load_config("sites.yaml")
    source = next(s for s in config.sources if s.id == "pokemon_official_products")
    with pytest.raises(ValueError):
        parse_pokemon_official_products(payload, API_URL, source, config)


def test_api_pagination_preserves_filter_and_stops_at_last_page() -> None:
    data = json.loads(_payload([{
        "productTitle": "拡張パック「テスト」", "productType": "拡張パック",
        "releaseDate": "2026年10月1日", "link_detailPage": "/ex/test/",
    }]))
    data.update(hitCnt=40, maxPage=2)
    urls = discover_pokemon_product_api_pages(json.dumps(data), API_URL)
    assert urls == [f"{API_URL}&page=2"]
    data["thisPage"] = 2
    assert discover_pokemon_product_api_pages(json.dumps(data), urls[0]) == []


@freeze_time("2026-09-30 12:00:00+09:00")
def test_zero_upcoming_products_is_healthy_without_browser_or_fallback(tmp_path: Path) -> None:
    config = load_config("sites.yaml")
    source = next(s for s in config.sources if s.id == "pokemon_official_products")
    config = replace(config, sources=[source])
    expected = pokemon_release_window_url(API_URL, 365, date(2026, 9, 30))
    calls: list[str] = []

    class Fetcher:
        def fetch(self, url: str, **_kwargs: object) -> FetchResult:
            calls.append(url)
            assert url == expected
            return FetchResult(url, 200, _payload([]), {})

    def no_browser(*_args: object) -> str:
        pytest.fail("A successful official API result must not require a browser")

    state = MonitorState.load(tmp_path / "state.json")
    cases, releases, alerts = run_pipeline(
        config, monitor_state=state,
        http_fetcher=Fetcher(), browser_fetcher=no_browser,  # type: ignore[arg-type]
    )
    assert calls == [expected]
    assert not cases and not releases and not alerts
    assert state.data["monitors"][source.id]["outcome"] == "success"
