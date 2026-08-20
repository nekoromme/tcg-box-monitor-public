from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import httpx

_ALLOWED_IMAGE_HOSTS = {
    "rts-pctr.c.yimg.jp",
    "pbs.twimg.com",
    "furu1.net",
    "www.furu1.net",
}
_MAX_IMAGE_BYTES = 8_000_000


def _suffix(content_type: str) -> str:
    folded = content_type.casefold()
    if "png" in folded:
        return ".png"
    if "webp" in folded:
        return ".webp"
    return ".jpg"


def read_image_text(urls: list[str]) -> str:
    """Download allowlisted monitored images and OCR them locally with Tesseract."""
    executable = shutil.which("tesseract")
    if not executable:
        raise RuntimeError("Tesseractがインストールされていません")

    output: list[str] = []
    failures: list[str] = []
    with (
        tempfile.TemporaryDirectory(prefix="tcg-ocr-") as directory,
        httpx.Client(follow_redirects=True, timeout=30) as client,
    ):
        for index, url in enumerate(dict.fromkeys(urls[:4])):
            parsed = urlsplit(url)
            if parsed.scheme != "https" or parsed.netloc not in _ALLOWED_IMAGE_HOSTS:
                continue
            try:
                response = client.get(
                    url,
                    headers={"User-Agent": "TCGBoxLotteryMonitor/2.0"},
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                # Yahoo image proxy URLs can expire while a direct X image in
                # the same post remains valid.  One broken image must not abort
                # OCR for every remaining attachment.
                failures.append(f"{type(exc).__name__}: {exc}")
                continue
            content_type = response.headers.get("content-type", "")
            if not content_type.casefold().startswith("image/"):
                failures.append(f"画像以外の応答: {content_type or 'unknown'}")
                continue
            if not response.content or len(response.content) > _MAX_IMAGE_BYTES:
                failures.append("画像が空、または上限サイズ超過")
                continue
            path = Path(directory) / f"tweet-{index}{_suffix(content_type)}"
            path.write_bytes(response.content)
            try:
                completed = subprocess.run(
                    [executable, str(path), "stdout", "-l", "jpn+eng", "--psm", "6"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=45,
                )
            except subprocess.TimeoutExpired:
                failures.append("Tesseract処理が45秒でタイムアウト")
                continue
            if completed.returncode == 0 and completed.stdout.strip():
                output.append(completed.stdout.strip())
            else:
                failures.append(
                    f"Tesseract終了コード{completed.returncode}: "
                    f"{completed.stderr.strip()[:120]}"
                )
    if not output:
        detail = " / ".join(failures[-2:])
        suffix = f"（{detail}）" if detail else ""
        raise RuntimeError(f"添付画像から文字を取得できませんでした{suffix}")
    return "\n".join(output)[:12_000]


__all__ = ["read_image_text"]
