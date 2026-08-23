from __future__ import annotations

import json
import logging
import sys


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")


def log_event(**kw: object) -> None:
    logging.info(json.dumps(kw, ensure_ascii=False, default=str))
