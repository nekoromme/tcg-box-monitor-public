from __future__ import annotations

import os
import re
from dataclasses import dataclass

import httpx

SECRET_PAT = re.compile(r"(https://discord(?:app)?\.com/api/webhooks/)[^\s]+")


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
