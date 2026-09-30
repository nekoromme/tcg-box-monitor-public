"""Independent, removable switches for the purchase-review trial only."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_REVIEW_MODES_PATH = "PURCHASE_REVIEW_MODES.txt"


class ReviewModeError(ValueError):
    """Invalid trial switches must not stop the main lottery monitor."""


@dataclass(frozen=True)
class PurchaseReviewModes:
    early_content: bool = False
    pre_release_price: bool = False


def load_purchase_review_modes(
    path: str | Path = DEFAULT_REVIEW_MODES_PATH,
) -> PurchaseReviewModes:
    """Missing file/entry means OFF; explicit valid entries opt into the trial."""
    switch_path = Path(path)
    if not switch_path.is_file():
        return PurchaseReviewModes()
    values: dict[str, bool] = {}
    for number, raw in enumerate(switch_path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip().upper()
        if (
            not separator
            or key not in {"EARLY_CONTENT", "PRE_RELEASE_PRICE"}
            or key in values
            or value not in {"ON", "OFF"}
        ):
            raise ReviewModeError(
                f"{switch_path}:{number} の試運転設定は EARLY_CONTENT / PRE_RELEASE_PRICE"
                " を一度ずつ、ON または OFF で指定してください"
            )
        values[key] = value == "ON"
    return PurchaseReviewModes(
        early_content=values.get("EARLY_CONTENT", False),
        pre_release_price=values.get("PRE_RELEASE_PRICE", False),
    )
