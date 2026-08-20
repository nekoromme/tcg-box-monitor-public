from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

import tcg_monitor.ocr as ocr


class _ImageResponse:
    def __init__(
        self,
        url: str,
        status_code: int,
        content: bytes,
        content_type: str = "image/jpeg",
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self) -> None:
        if self.status_code < 400:
            return
        request = httpx.Request("GET", self.url)
        response = httpx.Response(self.status_code, request=request)
        raise httpx.HTTPStatusError(
            f"HTTP {self.status_code}",
            request=request,
            response=response,
        )


class _ImageClient:
    def __init__(self, responses: dict[str, _ImageResponse]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def __enter__(self) -> _ImageClient:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def get(self, url: str, *, headers: dict[str, str]) -> _ImageResponse:
        assert headers["User-Agent"].startswith("TCGBoxLotteryMonitor/")
        self.calls.append(url)
        return self.responses[url]


def test_ocr_continues_after_one_expired_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expired = "https://rts-pctr.c.yimg.jp/expired"
    durable = "https://pbs.twimg.com/media/durable.jpg"
    client = _ImageClient(
        {
            expired: _ImageResponse(expired, 404, b""),
            durable: _ImageResponse(durable, 200, b"image-bytes"),
        }
    )
    monkeypatch.setattr(ocr.shutil, "which", lambda _name: "/usr/bin/tesseract")
    monkeypatch.setattr(ocr.httpx, "Client", lambda **_kwargs: client)
    monkeypatch.setattr(
        ocr.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="ポケモンカード 1BOX 抽選販売",
            stderr="",
        ),
    )

    result = ocr.read_image_text([expired, durable])

    assert result == "ポケモンカード 1BOX 抽選販売"
    assert client.calls == [expired, durable]


def test_ocr_allows_furuichi_official_news_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    official = (
        "https://www.furu1.net/storage/news/news_information/"
        "tl0822/20260811lpg.jpg"
    )
    client = _ImageClient(
        {official: _ImageResponse(official, 200, b"official-image-bytes")}
    )
    monkeypatch.setattr(ocr.shutil, "which", lambda _name: "/usr/bin/tesseract")
    monkeypatch.setattr(ocr.httpx, "Client", lambda **_kwargs: client)
    monkeypatch.setattr(
        ocr.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="抽選受付期間 2026年8月11日～8月16日23時まで",
            stderr="",
        ),
    )

    result = ocr.read_image_text([official])

    assert result.startswith("抽選受付期間")
    assert client.calls == [official]
