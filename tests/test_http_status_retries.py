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
