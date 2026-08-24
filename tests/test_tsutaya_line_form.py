from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import tcg_monitor.pipeline as pipeline
from tcg_monitor.config import load_config
from tcg_monitor.http_client import FetchResult
from tcg_monitor.models import SourceTier
from tcg_monitor.parsers.tsutaya_line import parse_tsutaya_line_form


def _source():  # type: ignore[no-untyped-def]
    return next(
        source
        for source in load_config("sites.yaml").sources
        if source.id == "yahoo_realtime_tsutaya_ichinoseki_store"
    )


def _form_payload(*, closed: bool = False) -> str:
    questions = [
        {
            "title": "希望商品を選択してください（複数選択可）",
            "questionInfo": json.dumps(
                {
                    "Choices": [
                        {"Description": "「拡張パック 30th CELEBRATION」"},
                        {
                            "Description": (
                                "「プレミアムデッキセット "
                                "エーフィ・ブラッキー」"
                            )
                        },
                    ]
                },
                ensure_ascii=False,
            ),
        },
        {
            "title": "希望店舗を選択してください（岩手県）",
            "questionInfo": json.dumps(
                {"Choices": [{"Description": "0412_TSUTAYA 一関店"}]},
                ensure_ascii=False,
            ),
        },
        {
            "title": "希望店舗を選択してください（宮城県）",
            "questionInfo": json.dumps(
                {
                    "Choices": [
                        {"Description": "0611_TSUTAYA 古川バイパス店"},
                        {"Description": "0616_TSUTAYA 築館店"},
                    ]
                },
                ensure_ascii=False,
            ),
        },
    ]
    return json.dumps(
        {
            "status": "Active",
            "title": (
                "【2026年9月】ポケモンカードゲーム MEGA "
                "拡張パック「30th CELEBRATION」抽選応募フォーム"
            ),
            "description": "受付は本フォームからのみとなります。",
            "settings": json.dumps(
                {
                    "FormClosed": closed,
                    "TimerEnabledEnd": True,
                    "EndTime": "2026-08-30T14:59:00+00:00",
                }
            ),
            "questions": questions,
        },
        ensure_ascii=False,
    )


def test_official_line_form_emits_each_target_store_without_deck_set() -> None:
    config = load_config("sites.yaml")
    source = _source()
    api_url = source.parser_options["always_fetch_urls"][0]

    cases, releases, alerts = parse_tsutaya_line_form(
        _form_payload(), api_url, source, config, date(2026, 8, 24)
    )

    assert not releases
    assert not alerts
    assert {case.retailer_id for case in cases} == {
        "tsutaya_ichinoseki_store",
        "tsutaya_tsukidate",
    }
    assert {case.product_name for case in cases} == {
        "「拡張パック 30th CELEBRATION」"
    }
    assert all(case.source_tier == SourceTier.OFFICIAL for case in cases)
    assert all(case.start_at == date(2026, 8, 24) for case in cases)
    assert all(
        case.end_at
        == datetime(2026, 8, 30, 23, 59, tzinfo=ZoneInfo("Asia/Tokyo"))
        for case in cases
    )
    assert all(case.official_url.startswith("https://liff.line.me/") for case in cases)
    assert all("tcg_campaign=2026-09" in case.official_url for case in cases)


def test_closed_official_line_form_is_healthy_and_emits_nothing() -> None:
    config = load_config("sites.yaml")
    source = _source()
    api_url = source.parser_options["always_fetch_urls"][0]

    cases, releases, alerts = parse_tsutaya_line_form(
        _form_payload(closed=True), api_url, source, config, date(2026, 8, 31)
    )

    assert not cases
    assert not releases
    assert not alerts


class _Fetcher:
    def __init__(self, responses: dict[str, FetchResult]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def fetch(
        self,
        url: str,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        del etag, last_modified
        self.calls.append(url)
        return self.responses[url]


def test_existing_store_source_always_fetches_shared_official_form() -> None:
    config = load_config("sites.yaml")
    source = _source()
    yahoo_url, twstalker_url, api_url = source.discovery_urls
    fetcher = _Fetcher(
        {
            yahoo_url: FetchResult(
                yahoo_url,
                200,
                "<main>一致する情報は見つかりませんでした</main>",
                {},
            ),
            api_url: FetchResult(api_url, 200, _form_payload(), {}),
        }
    )
    config = replace(
        config,
        sources=[source],
        system={
            **config.system,
            "minimum_host_interval_seconds": 0,
            "request_timeout_seconds": 1,
        },
    )

    cases, releases, alerts = pipeline.run_pipeline(
        config,
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert fetcher.calls == [yahoo_url, api_url]
    assert twstalker_url not in fetcher.calls
    assert len(cases) == 2
    assert not releases
    assert not alerts


def test_official_form_failure_is_not_hidden_by_healthy_store_x() -> None:
    config = load_config("sites.yaml")
    source = _source()
    yahoo_url, twstalker_url, api_url = source.discovery_urls
    fetcher = _Fetcher(
        {
            yahoo_url: FetchResult(
                yahoo_url,
                200,
                "<main>一致する情報は見つかりませんでした</main>",
                {},
            ),
            api_url: FetchResult(api_url, 503, "service unavailable", {}),
        }
    )
    config = replace(
        config,
        sources=[source],
        system={
            **config.system,
            "minimum_host_interval_seconds": 0,
            "request_timeout_seconds": 1,
        },
    )

    cases, releases, alerts = pipeline.run_pipeline(
        config,
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert fetcher.calls == [yahoo_url, api_url]
    assert twstalker_url not in fetcher.calls
    assert not cases
    assert not releases
    assert len(alerts) == 1
    assert alerts[0].target_url == api_url
    assert alerts[0].reason_code == "repeated_http_error"
