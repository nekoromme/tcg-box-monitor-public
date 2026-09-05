"""公式アカウントの検索漏れを補う経路。検索対象のアカウントは広げない。"""

from urllib.parse import parse_qs, quote, urlsplit

from tcg_monitor.models import SourceConfig, SourceTier


def social_discovery_urls(source: SourceConfig) -> list[str]:
    """キーワード検索の反映遅延に備え、公式アカウント単独の検索を併用する。

    二次情報アカウントには適用しない。他店の投稿まで流入させないため。
    投稿者・商品・応募条件の検査は、従来どおりパーサーが行う。
    """
    urls = list(source.discovery_urls)
    account = source.parser_options.get("account")
    if (
        source.parser_kind != "yahoo_realtime"
        or source.source_tier == SourceTier.SECONDARY
        or not isinstance(account, str)
        or not account
    ):
        return urls
    query = f"id:{account}"
    if any(
        urlsplit(url).netloc == "search.yahoo.co.jp"
        and parse_qs(urlsplit(url).query).get("p") == [query]
        for url in urls
    ):
        return urls
    urls.insert(1, f"https://search.yahoo.co.jp/realtime/search?p={quote(query)}&ei=UTF-8")
    return urls
