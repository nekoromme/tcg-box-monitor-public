"""指定した商品だけを抽選監視へ追加する共通処理。発売日監視は変更しない。"""

from __future__ import annotations

import re
import unicodedata

from tcg_monitor.models import ClassifiedProduct, Config, GameConfig, SourceConfig


def compact(value: str) -> str:
    # 全角・空白・中点の差（画像の文字認識を含む）を吸収する。
    return re.sub(r"[^0-9a-zぁ-んァ-ヶ一-龠ー]", "", unicodedata.normalize("NFKC", value).lower())


def additional_matches(game: GameConfig, text: str) -> list[ClassifiedProduct]:
    folded = compact(text)
    found = []
    for item in game.additional_products:
        if not item.enabled or not any(
            compact(alias) in folded for alias in (item.name, *item.aliases)
        ):
            continue
        # 種類名が書かれていれば個別に特定。書かれていない場合は商品群のまま通知。
        variants = [v for v in item.variants if compact(v) in folded]
        if item.selected_variants:
            variants = [v for v in variants if v in item.selected_variants]
            if not variants:
                continue
        names = [
            (f"{item.name} {v}", f"{item.id}:{item.variants.index(v) + 1}") for v in variants
        ] or [(item.name, item.id)]
        for name, key in names:
            found.append(
                ClassifiedProduct(
                    game.id.value,
                    name,
                    item.category,
                    False,
                    key,
                    ["additional_products:" + item.id],
                    [],
                    True,
                )
            )
    return found


def additional_game(text: str, source: SourceConfig, config: Config) -> str | None:
    games = [
        gid
        for gid, game in config.games.items()
        if source.supports(gid) and additional_matches(game, text)
    ]
    return games[0] if len(games) == 1 else None


def additional_tuples(game: GameConfig, text: str) -> list[tuple[str, str, str]]:
    return [
        (m.product_name, m.product_category, m.canonical_product_key)
        for m in additional_matches(game, text)
    ]


def without_additional_contents(game: GameConfig, text: str) -> str:
    """セット内のパック説明を別のBOX抽選として抽出しない。

    追加商品のある告知では、BOX数の明示がない拡張パック表記を除く。
    通常BOXの告知（追加商品なし）には適用しない。
    """
    if not additional_matches(game, text):
        return text
    categories = "|".join(map(re.escape, game.box_product_keywords))
    if not categories:
        return text
    pattern = re.compile(rf"(?:{categories})\s*[「『【\"“][^」』】\"”]+[」』】\"”]")

    def mask(match: re.Match[str]) -> str:
        after = text[match.end() : match.end() + 60]
        # 内容物の2パックなどより前にBOX数があれば独立したBOX商品とみなす。
        box = re.search(r"(?i)\b\d*BOX\b|ボックス", after)
        packs = re.search(r"[0-9０-９]+\s*パック", after)
        if box and (not packs or box.start() < packs.start()):
            return match.group(0)
        return " " * len(match.group(0))

    return pattern.sub(mask, text)
