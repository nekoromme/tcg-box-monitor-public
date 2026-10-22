from __future__ import annotations

import httpx
import pytest

from tcg_monitor.http_client import HttpFetcher


@pytest.mark.parametrize("status", [408, 500, 502, 503, 504])
def test_transient_http_response_recovers_within_existing_retry_budget(status: int) -> None:
    calls: list[str] = []

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(status if len(calls) == 1 else 200, text="official page")

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        fetcher = HttpFetcher(client=client, minimum_host_interval=0)
        result = fetcher.fetch("https://example.com/official-lottery")
    assert result.status_code == 200
    assert len(calls) == 2


@pytest.mark.parametrize("status,attempts", [(502, 3), (404, 1), (403, 1), (429, 1)])
def test_persistent_failure_is_preserved_and_access_gates_are_not_retried(
    status: int, attempts: int,
) -> None:
    calls: list[str] = []

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(status, text="failure")

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        result = HttpFetcher(client=client, minimum_host_interval=0).fetch("https://example.com/")
    assert result.status_code == status
    assert len(calls) == attempts


def test_response_retry_does_not_exceed_request_time_budget() -> None:
    calls: list[str] = []
    now = [0.0]

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(502, text="upstream unavailable")

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        result = HttpFetcher(
            client=client, minimum_host_interval=0, request_budget_seconds=1,
            max_retries=5, retry_backoff_seconds=(1,),
            _clock=lambda: now[0], _sleeper=lambda delay: now.__setitem__(0, now[0] + delay),
        ).fetch("https://example.com/")
    assert result.status_code == 502
    assert len(calls) == 1
    assert now[0] == 1


@pytest.mark.parametrize("headers,expected", [({}, [5, 15]), ({"Retry-After": "12"}, [12, 15])])
def test_service_unavailable_retries_wait_for_recovery(headers, expected) -> None:
    now = [100.0]
    calls: list[float] = []
    sleeps: list[float] = []

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(now[0])
        return httpx.Response(503 if len(calls) < 3 else 200, headers=headers)

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        result = HttpFetcher(
            client=client, minimum_host_interval=5, retry_backoff_seconds=(5, 15),
            _clock=lambda: now[0], _sleeper=sleep,
        ).fetch("https://example.com/")
    assert sleeps == expected
    assert result.status_code == 200
    assert result.attempts == 3
    assert calls == [100, 100 + expected[0], 100 + sum(expected)]


def test_long_retry_after_never_causes_an_early_second_request() -> None:
    now = [100.0]
    calls = []

    def response(request: httpx.Request) -> httpx.Response:
        calls.append(now[0])
        return httpx.Response(503, headers={"Retry-After": "120"})

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        result = HttpFetcher(
            client=client, request_budget_seconds=20, minimum_host_interval=5,
            _clock=lambda: now[0], _sleeper=lambda delay: now.__setitem__(0, now[0] + delay),
        ).fetch("https://example.com/")
    assert result.status_code == 503
    assert result.attempts == 1
    assert calls == [100]
    assert now[0] == 120


def test_http_failure_preserves_retry_count_and_cause_in_page_diagnostics() -> None:
    from tcg_monitor.config import load_config
    from tcg_monitor.fetching import FetchProblem, PageFetcher

    source = next(s for s in load_config("sites.yaml").sources
                  if s.id == "livepocket_hobby_station")
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(503, text="temporarily unavailable")
    )) as client:
        fetcher = HttpFetcher(client=client, minimum_host_interval=0)
        with pytest.raises(FetchProblem) as caught:
            PageFetcher(fetcher, lambda *args: "").fetch(source.discovery_urls[0], source, {})
    assert caught.value.cause_code == "http_status_503"
    assert caught.value.attempts == 3
