from __future__ import annotations

from tcg_monitor.models import Alert, SourceConfig


def health_alert(source: SourceConfig, url: str, status: int, text: str) -> Alert | None:
    if status in {403, 429} or status >= 500 or not text:
        return Alert(
            None,
            source.id,
            url,
            source.name,
            [],
            "repeated_http_error" if text else "empty_body",
            "健康監視異常",
            status,
            url,
        ).with_fingerprint()
    if any(x in text for x in ["Cloudflare", "CAPTCHA", "ログイン"]):
        return Alert(
            None,
            source.id,
            url,
            source.name,
            [],
            "login_or_error_replacement",
            "確認画面を検出",
            status,
            url,
        ).with_fingerprint()
    return None
