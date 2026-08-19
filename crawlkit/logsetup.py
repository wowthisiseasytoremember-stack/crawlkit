"""Logging configuration: human-readable console + optional rotating file log + JSON structured logs."""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

from .metrics import setup_structured_logging, JSONFormatter

_FMT = "%(asctime)s %(levelname)-7s %(name)-22s %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S"


class _ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[38;5;244m",
        "INFO": "\033[38;5;39m",
        "WARNING": "\033[38;5;214m",
        "ERROR": "\033[38;5;196m",
        "CRITICAL": "\033[1;97;41m",
    }
    RESET = "\033[0m"

    def __init__(self, use_color: bool):
        super().__init__(_FMT, _DATEFMT)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        if self.use_color:
            c = self.COLORS.get(record.levelname)
            if c:
                return f"{c}{msg}{self.RESET}"
        return msg


def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
    json_format: bool = False,
) -> None:
    """Configure logging with optional JSON structured output."""
    # Use structured logging if JSON format requested
    if json_format or os.getenv("CCARCHIVE_JSON_LOGS") == "1":
        setup_structured_logging(level=level, json_format=True)
        return

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for h in list(root.handlers):
        root.removeHandler(h)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.setFormatter(_ColorFormatter(use_color=sys.stderr.isatty()))
    root.addHandler(console)

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=32 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(_FMT, _DATEFMT))
        root.addHandler(fh)

    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)