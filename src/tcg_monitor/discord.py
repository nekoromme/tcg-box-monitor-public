from __future__ import annotations

import os
import re
from dataclasses import dataclass

import httpx

SECRET_PAT = re.compile(r"(https://discord(?:app)?\.com/api/webhooks/)[^\s]+")
# Discordの埋め込み本文上限4096文字に余裕を持たせる。
# 送信側の既存の4000文字カットより短くすることでURLを欠落させない。
DISCORD_SAFE_DESCRIPTION_LIMIT = 3800


def discord_text_length(text: str) -> int:
    """絵文字も余裕を持って数える。表示上1文字でも2文字分として扱う。"""
    return len(text.encode("utf-16-le")) // 2


def split_discord_description(
    description: str, limit: int = DISCORD_SAFE_DESCRIPTION_LIMIT,
) -> tuple[str, ...]:
    """改行を優先して分割し、URLと元の本文を一文字も捨てない。"""
    if limit < 2:
        raise ValueError("Discord通知の分割上限は2文字以上が必要です")
    parts: list[str] = []
    current = ""
    for line in description.splitlines(keepends=True):
        # 通常のURL行は丸ごと入れる。時刻一覧など1行自体が長い場合は
        # 空白の境界へ細分化し、空白のない長文だけ文字単位で分ける。
        tokens = ([line] if discord_text_length(line) <= limit
                  else re.findall(r"\S+|\s+", line))
        for token in tokens:
            if discord_text_length(token) > limit:
                if token.startswith(("https://", "http://")):
                    # 楽天の商品URLは短い。異常に長いURLまで黙って壊して
                    # 「通知済み」にせず、原因が分かるエラーで再試行対象に残す。
                    raise ValueError("Discord通知のURLが1件の文字数上限を超えています")
                pieces: list[str] = []
                piece = ""
                for char in token:
                    if discord_text_length(piece + char) > limit:
                        pieces.append(piece)
                        piece = ""
                    piece += char
                tokens_to_pack = [*pieces, piece]
            else:
                tokens_to_pack = [token]
            for piece in tokens_to_pack:
                if current and discord_text_length(current + piece) > limit:
                    parts.append(current)
                    current = ""
                current += piece
    if current or not parts:
        parts.append(current)
    return tuple(parts)


def mask_secret(s: str) -> str:
    return SECRET_PAT.sub(r"\1***", s).replace(os.getenv("DISCORD_WEBHOOK_URL", "\0"), "***")


@dataclass
class DiscordAdapter:
    webhook_url: str | None = None
    dry_run: bool = False

    def send(self, title: str, description: str) -> dict[str, str]:
        payload = {
            "content": None,
            "embeds": [{"title": title[:256], "description": description[:4000]}],
        }
        if self.dry_run or not (self.webhook_url or os.getenv("DISCORD_WEBHOOK_URL")):
            return {"status": "dry_run", "payload": str(payload)[:500]}
        try:
            r = httpx.post(
                (self.webhook_url or os.environ["DISCORD_WEBHOOK_URL"])
                + "?wait=true",
                json=payload,
                timeout=20,
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            # HTTPXの例外文には送信先URLが入ることがある。
            # GitHub側の自動マスクだけに頼らず、アプリ側でもWebhookを消す。
            raise RuntimeError(
                f"Discord通知の送信に失敗しました: {mask_secret(str(exc))}"
            ) from None
        return {"status": "sent"}
