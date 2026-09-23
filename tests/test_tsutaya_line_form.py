from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import tcg_monitor.pipeline as pipeline
from tcg_monitor.config import load_config
from tcg_monitor.http_client import FetchResult
from tcg_monitor.identity import lottery_dedupe_key
from tcg_monitor.models import SourceTier
from tcg_monitor.parsers.tsutaya_line import parse_tsutaya_line_form
from tcg_monitor.source_priority import merge_lotteries
from tcg_monitor.state import MonitorState


def _source():  # type: ignore[no-untyped-def]
    return next(
        source
        for source in load_config("sites.yaml").sources
        if source.id == "yahoo_realtime_tsutaya_ichinoseki_store"
    )


def _form_payload(
    *,
    closed: bool = False,
    include_ichinoseki: bool = True,
    include_tsukidate: bool = True,
) -> str:
    iwate_choices = [{"Description": "0412_TSUTAYA 一関店"}] if include_ichinoseki else []
    miyagi_choices = [{"Description": "0611_TSUTAYA 古川バイパス店"}]
    if include_tsukidate:
        miyagi_choices.append({"Description": "0616_TSUTAYA 築館店"})
    questions = [
        {
            "title": "希望商品を選択してください（複数選択可）",
            "questionInfo": json.dumps(
                {
                    "Choices": [
                        {"Description": "「拡張パック 30th CELEBRATION」"},
                        {"Description": ("「プレミアムデッキセット エーフィ・ブラッキー」")},
                    ]
                },
                ensure_ascii=False,
            ),
        },
        {
            "title": "希望店舗を選択してください（岩手県）",
            "questionInfo": json.dumps(
                {"Choices": iwate_choices},
                ensure_ascii=False,
            ),
        },
        {
            "title": "希望店舗を選択してください（宮城県）",
            "questionInfo": json.dumps(
                {"Choices": miyagi_choices},
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


def test_official_line_form_groups_both_target_stores_without_deck_set() -> None:
    config = load_config("sites.yaml")
    source = _source()
    api_url = source.parser_options["always_fetch_urls"][0]

    cases, releases, alerts = parse_tsutaya_line_form(
        _form_payload(), api_url, source, config, date(2026, 8, 24)
    )

    assert not releases
    assert not alerts
    assert len(cases) == 1
    assert cases[0].retailer_id == "tsutaya_ichinoseki_store"
    assert cases[0].retailer_name == "TSUTAYA公式LINE抽選（対象: 一関店・築館店）"
    # Keep the already-delivered Ichinoseki identity so grouping cannot notify again.
    assert cases[0].case_id == "a18503c74ab3735444f09ceff5e412d112169f328ad77a17853dd2c94bb3e371"
    assert {case.product_name for case in cases} == {"「拡張パック 30th CELEBRATION」"}
    assert all(case.source_tier == SourceTier.OFFICIAL for case in cases)
    assert all(case.start_at == date(2026, 8, 24) for case in cases)
    assert all(
        case.end_at == datetime(2026, 8, 30, 23, 59, tzinfo=ZoneInfo("Asia/Tokyo"))
        for case in cases
    )
    assert all(case.official_url.startswith("https://liff.line.me/") for case in cases)
    assert all("tcg_campaign=2026-09" in case.official_url for case in cases)


def test_official_line_form_emits_one_group_case_when_either_store_is_present() -> None:
    config = load_config("sites.yaml")
    source = _source()
    api_url = source.parser_options["always_fetch_urls"][0]

    for include_ichinoseki, include_tsukidate, expected_label in (
        (True, False, "一関店"),
        (False, True, "築館店"),
    ):
        cases, releases, alerts = parse_tsutaya_line_form(
            _form_payload(
                include_ichinoseki=include_ichinoseki,
                include_tsukidate=include_tsukidate,
            ),
            api_url,
            source,
            config,
            date(2026, 8, 24),
        )

        assert len(cases) == 1
        assert cases[0].retailer_id == "tsutaya_ichinoseki_store"
        assert cases[0].retailer_name == (f"TSUTAYA公式LINE抽選（対象: {expected_label}）")
        assert not releases
        assert not alerts

    cases, releases, alerts = parse_tsutaya_line_form(
        _form_payload(include_ichinoseki=False, include_tsukidate=False),
        api_url,
        source,
        config,
        date(2026, 8, 24),
    )
    assert not cases
    assert not releases
    assert not alerts


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
    yahoo_url, twstalker_url, api_url, cardset_url = source.discovery_urls
    fetcher = _Fetcher(
        {
            yahoo_url: FetchResult(
                yahoo_url,
                200,
                "<main>一致する情報は見つかりませんでした</main>",
                {},
            ),
            api_url: FetchResult(api_url, 200, _form_payload(), {}),
            cardset_url: FetchResult(cardset_url, 200, _cardset_payload(), {}),
        }
    )
    config = replace(
        config,
        sources=[source],
        system={
            **config.system,
            "minimum_host_interval_seconds": 0,
            "request_timeout_seconds": 1,
            "social_account_fallback": False,
        },
    )

    cases, releases, alerts = pipeline.run_pipeline(
        config,
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert fetcher.calls == [yahoo_url, api_url, cardset_url]
    assert twstalker_url not in fetcher.calls
    # 通常BOX1件と、9種類をまとめたカードセット1件。
    assert len(cases) == 2
    assert sum(c.canonical_product_key == "pokemon_30th_cardset" for c in cases) == 1
    assert not releases
    assert not alerts


def test_official_form_failure_is_not_hidden_by_healthy_store_x() -> None:
    config = load_config("sites.yaml")
    source = _source()
    yahoo_url, twstalker_url, api_url, cardset_url = source.discovery_urls
    fetcher = _Fetcher(
        {
            yahoo_url: FetchResult(
                yahoo_url,
                200,
                "<main>一致する情報は見つかりませんでした</main>",
                {},
            ),
            api_url: FetchResult(api_url, 503, "service unavailable", {}),
            cardset_url: FetchResult(cardset_url, 200, '{"error":{"code":"5003"}}', {}),
        }
    )
    config = replace(
        config,
        sources=[source],
        system={
            **config.system,
            "minimum_host_interval_seconds": 0,
            "request_timeout_seconds": 1,
            "social_account_fallback": False,
        },
    )

    cases, releases, alerts = pipeline.run_pipeline(
        config,
        http_fetcher=fetcher,  # type: ignore[arg-type]
    )

    assert fetcher.calls == [yahoo_url, api_url, cardset_url]
    assert twstalker_url not in fetcher.calls
    assert not cases
    assert not releases
    assert len(alerts) == 1
    assert alerts[0].target_url == api_url
    assert alerts[0].reason_code == "repeated_http_error"


def _cardset_payload() -> str:
    return Path("tests/fixtures/tsutaya_line_cardset.json").read_text()


def test_live_cardset_variant_choices_and_campaign_links() -> None:
    config = load_config("sites.yaml")
    source = _source()
    form = source.parser_options["tsutaya_line_forms"][0]
    cases, _, _ = parse_tsutaya_line_form(
        _cardset_payload(), form["api_url"], source, config, date(2026, 9, 21)
    )
    assert len(cases) == 9
    assert len({case.case_id for case in cases}) == 9
    assert all(case.product_category == "カードセット" for case in cases)
    assert all(case.product_name.startswith("30th CELEBRATION カードセット ") for case in cases)
    assert all(case.result_at == date(2026, 10, 9) for case in cases)
    assert all(case.retailer_name.endswith("（対象: 一関店・築館店）") for case in cases)
    assert all(case.source_url == form["public_form_url"] for case in cases)
    assert all("WALLET_ADDRESS" in case.official_url for case in cases)
    assert all("LINE_UID" in case.official_url for case in cases)
    assert all(
        case.end_at == datetime(2026, 9, 28, tzinfo=ZoneInfo("Asia/Tokyo")) for case in cases
    )
    from urllib.parse import parse_qs, urlsplit

    assert parse_qs(urlsplit(cases[0].official_url).query)["formUrl"] == [form["public_form_url"]]


def test_confirmed_result_date_does_not_leak_to_a_reused_form() -> None:
    config = load_config("sites.yaml")
    source = _source()
    form = source.parser_options["tsutaya_line_forms"][0]
    changed = json.loads(_cardset_payload())
    changed["title"] = changed["title"].replace("2026年10月16日発売", "2026年11月16日発売").replace(
        "カードセット9種", "カードセット次回9種"
    )

    cases, _, _ = parse_tsutaya_line_form(
        json.dumps(changed, ensure_ascii=False), form["api_url"], source, config,
        date(2026, 9, 21),
    )
    assert cases
    assert all(case.result_at is None for case in cases)


def test_cardset_form_keeps_notification_identity_across_daily_scans(tmp_path: Path) -> None:
    config = load_config("sites.yaml")
    source = _source()
    form = source.parser_options["tsutaya_line_forms"][0]

    def grouped_on(day: date):  # type: ignore[no-untyped-def]
        cases, _, _ = parse_tsutaya_line_form(
            _cardset_payload(), form["api_url"], source, config, day
        )
        return merge_lotteries(cases)[0][0]

    first = grouped_on(date(2026, 9, 22))
    following = grouped_on(date(2026, 9, 23))
    assert first.case_id == following.case_id
    assert first.result_at == following.result_at == date(2026, 10, 9)

    # The earlier date-based ID was delivered already. Upgrade its journal
    # record instead of sending one more notification during the first run.
    state = MonitorState(tmp_path / "state.json")
    old_identity = replace(
        first,
        case_id=sha256(lottery_dedupe_key(first).encode()).hexdigest(),
    )
    state.data["seen_cases"][old_identity.case_id] = {
        **old_identity.__dict__, "start_at": "2026-09-22",
    }
    state.data["delivery_journal"][f"lottery:started:{old_identity.case_id}"] = {
        "status": "complete", "updated_at": "2026-09-22T10:00:00+09:00",
    }
    assert state.migrate_case_identity(following) == old_identity.case_id
    assert state.delivered(f"lottery:started:{following.case_id}")

    # A different form is a separate application even for the same product.
    next_form = replace(following, official_url=following.official_url + "&formUrl=new")
    assert merge_lotteries([next_form])[0][0].case_id != following.case_id


def test_variant_choices_require_opt_in_and_matching_form_title() -> None:
    config = load_config("sites.yaml")
    source = _source()
    url = source.parser_options["tsutaya_line_forms"][0]["api_url"]
    game = config.games["pokemon_card"]
    item = game.additional_products[0]
    for products, expected in (
        ((), 0),
        ((replace(item, enabled=False),), 0),
        ((replace(item, selected_variants=(item.variants[0],)),), 1),
    ):
        changed = replace(
            config,
            games={**config.games, "pokemon_card": replace(game, additional_products=products)},
        )
        cases, _, _ = parse_tsutaya_line_form(_cardset_payload(), url, source, changed)
        assert len(cases) == expected
    payload = json.loads(_cardset_payload())
    payload["title"] = "ポケモンカードゲーム 別商品 抽選"
    cases, _, _ = parse_tsutaya_line_form(json.dumps(payload), url, source, config)
    assert not cases


def test_unknown_api_errors_are_not_treated_as_closed_forms() -> None:
    config = load_config("sites.yaml")
    source = _source()
    url = source.parser_options["always_fetch_urls"][0]
    for payload in ('{"error":{"code":"5000"}}', "{}"):
        with pytest.raises(ValueError):
            parse_tsutaya_line_form(payload, url, source, config)
    assert parse_tsutaya_line_form('{"error":{"code":"5003"}}', url, source, config) == ([], [], [])
