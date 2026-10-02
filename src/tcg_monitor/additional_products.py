"""指定商品と限定セット系列を抽選へ追加する共通処理。発売日監視は変更しない。"""

from __future__ import annotations

import re
import unicodedata
from hashlib import sha256

from tcg_monitor.models import ClassifiedProduct, Config, GameConfig, SourceConfig


def compact(value: str) -> str:
    # 全角・空白・中点の差（画像の文字認識を含む）を吸収する。
    return re.sub(r"[^0-9a-zα-ωぁ-んァ-ヶ一-龠ー]", "",
                  unicodedata.normalize("NFKC", value).lower())


def _family_name(game: GameConfig, value: str) -> str:
    """商品名の表記差を消すが、絵柄・周年・開催地などの識別部分は残す。"""
    value = re.sub(r'[「」『』【】"“”]', " ", value)
    value = re.sub(r"\s+", " ", value).strip(" 　・")
    for prefix in sorted((*game.include_keywords, game.name), key=len, reverse=True):
        if value.startswith(prefix):
            value = value[len(prefix):].lstrip()
    value = re.sub(r"^(?:MEGA|スカーレット[&＆]バイオレット)\s*", "", value)
    value = re.sub(r"^(?:強化拡張パック|ハイクラスパック|拡張パック)\s*", "", value)
    return value.strip(" 　・「」『』【】\"“”")


def additional_matches(
    game: GameConfig, text: str, *, identified_game: bool = False,
) -> list[ClassifiedProduct]:
    folded = compact(text)
    found: list[ClassifiedProduct] = []
    # 従来の個別指定・OFF・種類選択を系列ルールで上書きしない。
    reserved = [alias for item in game.additional_products if not item.name_patterns
                for alias in (item.name, *item.aliases) if compact(alias) in folded]
    for item in game.additional_products:
        if item.required_keywords and not any(
            compact(word) in folded for word in item.required_keywords
        ):
            continue
        if any(compact(word) in folded for word in item.exclude_keywords):
            continue
        if item.name_patterns:
            if not item.enabled:
                continue
            normalized = unicodedata.normalize("NFKC", text)
            matched_spans: list[tuple[int, int]] = []
            for pattern in item.name_patterns:
                for match in re.finditer(pattern, normalized, re.I):
                    if any(match.start() < end and match.end() > start
                           for start, end in matched_spans):
                        continue  # 同じ系列の長い正式名を短い別表記で二重検出しない。
                    if item.require_game_identity and not identified_game:
                        nearby = compact(normalized[max(0, match.start() - 140):match.end() + 60])
                        if not any(compact(word) in nearby for word in game.include_keywords):
                            continue  # 共通の周年名を別作品へ割り当てない。
                    if re.match(
                        r"\s*(?:の|用)?(?:プレイマット|スリーブ|カードケース|デッキケース|単品|単体)",
                        normalized[match.end():match.end() + 32],
                    ):
                        continue  # 系列名を使った用品単品をセットと誤認しない。
                    name = _family_name(game, match.group("name"))
                    if not name or any(
                        compact(alias) in compact(name) or compact(name) in compact(alias)
                        for alias in reserved
                    ):
                        continue
                    if name in {item.name, "開催記念デュエルセット", "記念デュエルセット"}:
                        continue  # 商品名のない見出しを独立商品にしない。
                    key = f"nonbox:{item.id}:{compact(name)}"
                    if len(key) > 80:
                        key = f"nonbox:{item.id}:" + sha256(compact(name).encode()).hexdigest()
                    if any(product.canonical_product_key == key for product in found):
                        continue
                    matched_spans.append(match.span())
                    found.append(ClassifiedProduct(
                        game.id.value, name, item.category, False, key,
                        ["additional_products:" + item.id, "non_box_family_candidate"], [], True,
                    ))
            continue
        if not item.enabled or not any(
            compact(alias) in folded for alias in (item.name, *item.aliases)
        ):
            continue
        if any(re.search(
            re.escape(compact(alias)) + r"(?:(?:の|用)(?:スリーブ|プレイマット|カードケース)|"
            r"(?:スリーブ|プレイマット|カードケース|サプライ)(?:単品|単体|のみ))", folded,
        ) for alias in (item.name, *item.aliases)):
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


def additional_note(game: GameConfig, product_key: str) -> str:
    parts = product_key.split(":")
    item_id = parts[1] if parts[0] == "nonbox" and len(parts) > 1 else parts[0]
    return next(
        (item.note for item in game.additional_products
         if item.id == item_id and item.enabled), "",
    )


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
    # パックを同梱するカードセットだけが対象。デッキセットと並べて
    # 告知された通常の拡張パックを、同梱物と誤認して消さない。
    if not any(m.product_category in {
        "特別セット", "先行限定セット", "カードセット", "スペシャルBOX",
        "ポケモンセンターセット", "アニバーサリーセット",
    } for m in additional_matches(game, text)):
        return text
    categories = "|".join(map(re.escape, game.box_product_keywords))
    if not categories:
        return text
    pattern = re.compile(rf"(?:{categories})\s*[「『【\"“][^」』】\"”]+[」』】\"”]")

    def mask(match: re.Match[str]) -> str:
        before = text[max(0, match.start() - 60):match.start()]
        if re.search(r"内容物|セット内容|同梱", before):
            return " " * len(match.group(0))
        after = text[match.end() : match.end() + 60]
        # 内容物の2パックなどより前にBOX数があれば独立したBOX商品とみなす。
        box = re.search(r"(?i)\b\d*BOX\b|ボックス", after)
        packs = re.search(r"[0-9０-９]+\s*パック", after)
        if box and (not packs or box.start() < packs.start()):
            return match.group(0)
        return " " * len(match.group(0))

    return pattern.sub(mask, text)
