from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo


def identified_browser_user_agent(
    chromium_version: str,
    contact: str = "",
) -> str:
    """Keep Chromium's browser-shaped UA while identifying this monitor."""

    safe_version = chromium_version.strip() or "0.0.0.0"
    identity = "TCGBoxLotteryMonitor/2.0"
    safe_contact = contact.replace("\r", "").replace("\n", "").strip()
    if safe_contact:
        identity += f" (+{safe_contact})"
    return (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{safe_version} Safari/537.36 {identity}"
    )


def pokemon_release_window_url(
    url: str, max_future_days: int, today: date | None = None
) -> str:
    """Add the official catalog's date window without removing productType."""
    start = today or datetime.now(ZoneInfo("Asia/Tokyo")).date()
    end = start + timedelta(days=max_future_days)
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(
        {
            "dateLowerY": str(start.year),
            "dateLowerM": str(start.month),
            "dateLowerD": str(start.day),
            "dateUpperY": str(end.year),
            "dateUpperM": str(end.month),
            "dateUpperD": str(end.day),
        }
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def fetch_rendered_html(
    url: str, wait_selector: str | None = None, timeout_ms: int = 30_000
) -> str:
    """Render one public page. Import Playwright lazily so HTTP-only runs stay light."""
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "Playwrightが未導入です。browser extraをインストールしてください"
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            # A bare bot token is valid for HTTP fetches but is not a realistic
            # browser UA.  Some public shops reject it before navigation even
            # though the same Chromium build is allowed with its normal UA.
            # Preserve the real Chromium version and append our identity.
            user_agent = identified_browser_user_agent(
                browser.version,
                os.getenv("MONITOR_USER_AGENT_CONTACT", ""),
            )
            page = browser.new_page(user_agent=user_agent, locale="ja-JP")
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if wait_selector:
                page.wait_for_selector(wait_selector, timeout=timeout_ms)
            return str(page.content())
        finally:
            browser.close()
