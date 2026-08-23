from __future__ import annotations

from typing import Protocol

from tcg_monitor.models import Alert, Config, LotteryCase, Release, SourceConfig


class Parser(Protocol):
    def parse(
        self, html: str, url: str, source: SourceConfig, config: Config
    ) -> tuple[list[LotteryCase], list[Release], list[Alert]]: ...
