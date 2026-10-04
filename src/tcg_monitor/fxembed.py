"""公開X投稿の補完取得。ユーザーの認証情報・ブラウザーは使わない。

取得だけを担当し、応募条件・商品・通知済み判定は既存処理へ渡す。
引用先や他人のリポストを元アカウントの募集として混ぜない。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any
from urllib.parse import urlencode, urlsplit

from tcg_monitor.fetching import FetchProblem, PageFetcher, PageResult
from tcg_monitor.models import RenderMode, SourceConfig

BASE = "https://api.fxtwitter.com/2/profile/"
X_EPOCH_MS = 1288834974657


def timeline_url(source: SourceConfig) -> str | None:
    account = source.parser_options.get("account")
    if source.parser_kind != "yahoo_realtime" or not isinstance(account, str):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", account):
        return None
    return f"{BASE}{account.lower()}/statuses?count=20"


def is_fxembed_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.netloc == "api.fxtwitter.com"


def _public_link(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parts = urlsplit(value)
    if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username:
        return None
    return value


def _status_reference(url: str) -> bool:
    parts = urlsplit(url)
    return (parts.netloc.lower().removeprefix("www.") in {"x.com", "twitter.com"}
            and bool(re.search(r"/status/\d+", parts.path)))


def post_markup(post: dict[str, Any], account: str) -> str | None:
    """自分の本文・添付写真・リンクだけを既存パーサー用の形へ変換する。"""
    author = post.get("author")
    if not isinstance(author, dict) or str(author.get("screen_name", "")).lower() != account:
        return None  # リポスト元や引用先のアカウントを監視対象へ拡張しない。
    status_id = str(post.get("id", ""))
    text = post.get("text")
    if not status_id.isdigit() or not isinstance(text, str) or not text.strip():
        return None
    if post.get("tombstone"):
        return None
    url = f"https://x.com/{account}/status/{status_id}"
    links: list[str] = []
    raw = post.get("raw_text")
    facets = raw.get("facets", []) if isinstance(raw, dict) else []
    for facet in facets if isinstance(facets, list) else []:
        if (isinstance(facet, dict) and facet.get("type") == "url"
                and (link := _public_link(facet.get("replacement")))):
            links.append(link)
    links.extend(re.findall(r"https?://[^\s<>]+", text))
    media = post.get("media")
    photos = media.get("photos", []) if isinstance(media, dict) else []
    images: list[str] = []
    for photo in photos if isinstance(photos, list) else []:
        link = _public_link(photo.get("url")) if isinstance(photo, dict) else None
        if link and urlsplit(link).netloc == "pbs.twimg.com" and "/media/" in link:
            images.append(link)
    # 本文を必ずエスケープする。投稿内のHTMLや引用カードは解釈しない。
    body = escape(text).replace("\n", "<br/>")
    markup = f'<article><p class="Tweet_body">{body}</p><a href="{url}">投稿</a>'
    markup += "".join(f'<a href="{escape(link, quote=True)}">リンク</a>'
                      for link in dict.fromkeys(links)
                      if _public_link(link) and not _status_reference(link))
    # 従来のハッシュタグによる商品名補完も維持する。
    markup += "".join(
        f'<a href="/realtime/search?p=%23{escape(tag, quote=True)}">#{escape(tag)}</a>'
        for tag in re.findall(r"[#＃]([\wー]+)", text)
    )
    markup += "".join(f'<img src="{escape(link, quote=True)}"/>' for link in images[:4])
    return markup + "</article>"


@dataclass
class FxEmbedReader:
    page_fetcher: PageFetcher
    # 前回最後に網羅できた範囲。途中失敗時に更新すると、その間が永久に欠落する。
    watermarks: dict[str, Any]
    max_pages: int = 5
    lookback_days: int = 7
    snapshots: dict[str, PageResult | FetchProblem] = field(default_factory=dict)
    reports: dict[str, dict[str, object]] = field(default_factory=dict)

    def fetch(self, url: str, source: SourceConfig) -> PageResult:
        root = timeline_url(source)
        if root != url:
            raise ValueError("FxEmbed URL does not match configured account")
        cached = self.snapshots.get(url)
        if isinstance(cached, FetchProblem):
            raise cached
        if cached is not None:
            return cached  # 共通アカウントを複数作品・店舗で使っても通信は1回。
        try:
            result = self._read(url, source)
        except FetchProblem as exc:
            self.snapshots[url] = exc
            raise
        self.snapshots[url] = result
        return result

    def _read(self, url: str, source: SourceConfig) -> PageResult:
        account = str(source.parser_options["account"]).lower()
        # 取得元で304だけ返ると本文・画像を再解析できないため条件付き取得を使わない。
        http_source = replace(source, render_mode=RenderMode.HTTP, parser_options={
            **source.parser_options, "disable_conditional_get": True,
        })
        cutoff = int((datetime.now(UTC) - timedelta(days=self.lookback_days)).timestamp())
        previous = str(self.watermarks.get(account, ""))
        previous_id = int(previous) if previous.isdigit() else 0
        newest_id = 0
        seen: set[str] = set()
        cursors: set[str] = set()
        markup: list[str] = []
        report: dict[str, object] = {
            "provider": "fxembed", "pages": 0, "posts": 0, "complete": False,
        }
        self.reports[url] = report
        next_url = url
        duration = 0
        for page in range(max(1, self.max_pages)):
            try:
                response = self.page_fetcher.fetch(next_url, http_source, {})
                duration += response.duration_ms
                payload = json.loads(response.html)
                if not isinstance(payload, dict) or payload.get("code") != 200:
                    raise ValueError("FxEmbed returned a non-success payload")
                rows = payload.get("results")
                if not isinstance(rows, list) or payload.get("error"):
                    raise ValueError("FxEmbed results missing or partial error")
            except (FetchProblem, ValueError) as exc:
                if not markup:
                    if isinstance(exc, FetchProblem):
                        raise
                    raise FetchProblem(url, "fxembed_invalid_payload") from exc
                report["incomplete_reason"] = (
                    exc.reason if isinstance(exc, FetchProblem) else "invalid_payload"
                )
                break  # 取得済み本文は使い、不完全であることも通知・ログへ残す。
            report["pages"] = page + 1
            new_rows = 0
            for post in rows:
                if not isinstance(post, dict):
                    raise FetchProblem(url, "fxembed_invalid_post")
                status_id = str(post.get("id", ""))
                if not status_id.isdigit() or status_id in seen:
                    continue
                seen.add(status_id)
                new_rows += 1
                rendered = post_markup(post, account)
                if rendered is None:
                    continue
                sid = int(status_id)
                timestamp = ((sid >> 22) + X_EPOCH_MS) // 1000
                # 固定投稿1件が古いだけで後続ページを止めない。下でページ全体を検査。
                newest_id = max(newest_id, sid)
                if timestamp >= cutoff:
                    markup.append(rendered)
            report["posts"] = len(markup)
            cursor = payload.get("cursor")
            bottom = cursor.get("bottom") if isinstance(cursor, dict) else None
            # 固定投稿・リポストの古いIDを除外し、通常投稿の末尾で期間を判断する。
            own_rows = [p for p in rows if isinstance(p, dict)
                        and post_markup(p, account) is not None and not p.get("is_pinned")
                        and not p.get("reposted_by")]
            old_tail = bool(own_rows) and all(
                ((int(str(p["id"])) >> 22) + X_EPOCH_MS) // 1000 < cutoff
                for p in own_rows[-3:]
            )
            reached_boundary = bool(previous_id and own_rows) and all(
                int(str(p["id"])) <= previous_id for p in own_rows[-3:]
            )
            if reached_boundary or old_tail or not rows or not bottom:
                report["complete"] = True
                break
            if not isinstance(bottom, str) or bottom in cursors or new_rows == 0:
                report["incomplete_reason"] = "repeated_or_invalid_cursor"
                break
            cursors.add(bottom)
            next_url = url + "&" + urlencode({"cursor": bottom})
        if not report["complete"]:
            report.setdefault("incomplete_reason", "page_limit")
        elif newest_id:
            self.watermarks[account] = str(newest_id)
        # 空の成功応答もHTML解析へ渡せる形にする。0件と取得失敗を区別する。
        return PageResult(url, "<main>" + "\n".join(markup) + "</main>",
                          200, "fxembed_public", duration_ms=duration)
