from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PIL import Image, UnidentifiedImageError

_ALLOWED_IMAGE_HOSTS = {
    "rts-pctr.c.yimg.jp",
    "pbs.twimg.com",
    "furu1.net",
    "www.furu1.net",
}
_MAX_IMAGE_BYTES = 8_000_000


def _color_text_variant(path: Path, destination: Path) -> Path | None:
    """赤い応募日が通常の文字認識で消える場合に備え、文字の濃淡を強める。"""
    try:
        with Image.open(path) as original:
            if original.width * original.height > 20_000_000:
                return None
            # 赤字は緑成分が小さい。黒字とともに黒くし、白い背景を維持する。
            channel = original.convert("RGB").getchannel("G")
            enlarged = channel.resize((original.width * 2, original.height * 2))
            enlarged.point([0] * 161 + [255] * 95).save(destination)
    except (OSError, UnidentifiedImageError):
        return None
    return destination


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
    read_images = 0
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
            variants = [path]
            enhanced = _color_text_variant(path, Path(directory) / f"text-{index}.png")
            if enhanced is not None:
                variants.append(enhanced)
            for variant in variants:
                try:
                    completed = subprocess.run(
                        [executable, str(variant), "stdout", "-l", "jpn+eng", "--psm", "6"],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=45,
                    )
                except subprocess.TimeoutExpired:
                    failures.append("Tesseract処理が45秒でタイムアウト")
                    continue
                if completed.returncode == 0:
                    read_images += 1
                    recognized = completed.stdout.strip()
                    if recognized and recognized not in output:
                        output.append(recognized)
                else:
                    failures.append(
                        f"Tesseract終了コード{completed.returncode}: "
                        f"{completed.stderr.strip()[:120]}"
                    )
    if not output:
        # 写真などの「読取成功・文字なし」と、取得／処理の失敗を区別する。
        # 抽選の本文がある場合は呼び出し側が引き続き読取不足として扱う。
        if read_images and not failures:
            return ""
        detail = " / ".join(failures[-2:])
        suffix = f"（{detail}）" if detail else ""
        raise RuntimeError(f"添付画像から文字を取得できませんでした{suffix}")
    return "\n".join(output)[:12_000]


__all__ = ["read_image_text"]
