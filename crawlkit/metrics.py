"""Structured logging and metrics for ccarchive."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Try to import prometheus_client for metrics
try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

log = logging.getLogger(__name__)


@dataclass
class Metrics:
    """Prometheus metrics for ccarchive."""

    stories_total: Any = None
    extraction_duration: Any = None
    errors_total: Any = None
    queue_depth: Any = None
    cdp_connections: Any = None
    classification_confidence: Any = None

    def __post_init__(self):
        if not PROMETHEUS_AVAILABLE:
            return
        self.stories_total = Counter(
            "ccarchive_stories_total",
            "Total stories processed",
            ["site", "niche", "outcome"],
        )
        self.extraction_duration = Histogram(
            "ccarchive_extraction_duration_seconds",
            "Story extraction duration",
            ["site"],
            buckets=[0.5, 1, 2, 5, 10, 30, 60, 120, 300],
        )
        self.errors_total = Counter(
            "ccarchive_errors_total",
            "Total errors by type",
            ["site", "error_type"],
        )
        self.queue_depth = Gauge(
            "ccarchive_queue_depth",
            "Discovery queue depth",
            ["site", "state"],
        )
        self.cdp_connections = Gauge(
            "ccarchive_cdp_connections",
            "Active CDP connections",
        )
        self.classification_confidence = Histogram(
            "ccarchive_classification_confidence",
            "Classification confidence score",
            ["niche"],
            buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        )


@dataclass
class StructuredLogger:
    """JSON-structured logger for production."""

    logger: logging.Logger
    extra_fields: dict[str, Any] = field(default_factory=dict)

    def _log(self, level: int, message: str, **kwargs) -> None:
        extra = {**self.extra_fields, **kwargs}
        # Filter out None values
        extra = {k: v for k, v in extra.items() if v is not None}
        self.logger.log(level, message, extra=extra)

    def info(self, message: str, **kwargs) -> None:
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        self._log(logging.ERROR, message, **kwargs)

    def debug(self, message: str, **kwargs) -> None:
        self._log(logging.DEBUG, message, **kwargs)

    def bind(self, **kwargs) -> StructuredLogger:
        return StructuredLogger(self.logger, {**self.extra_fields, **kwargs})

    @contextmanager
    def timer(self, operation: str, **kwargs):
        start = time.monotonic()
        try:
            yield
        finally:
            duration = time.monotonic() - start
            self.info(f"{operation} completed", duration_seconds=duration, **kwargs)


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "exc_info",
                "exc_text",
                "stack_info",
            }:
                data[key] = value

        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)

        return json.dumps(data, ensure_ascii=False)


def setup_structured_logging(level: str = "INFO", json_format: bool = False) -> None:
    """Configure structured logging."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    if json_format or os.getenv("CCARCHIVE_JSON_LOGS") == "1":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s %(name)s %(message)s",
                datefmt="%H:%M:%S",
            )
        )
    root.addHandler(handler)

    # Reduce noise from playwright
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def start_metrics_server(port: int = 9090) -> bool:
    """Start Prometheus metrics HTTP server."""
    if not PROMETHEUS_AVAILABLE:
        log.warning("prometheus_client not installed; metrics server not started")
        return False
    try:
        start_http_server(port)
        log.info("Prometheus metrics server started on port %d", port)
        return True
    except Exception as e:
        log.error("Failed to start metrics server: %s", e)
        return False


# Global metrics instance
METRICS = Metrics()


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger with default context."""
    return StructuredLogger(logging.getLogger(name))