"""
Echo-Orchestra logging setup.
Structured logs with a rotating file handler plus a console handler.
Replaces ad-hoc print() calls across the system.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path


_CONFIGURED = False


def setup_logging(
    log_dir: str | None = None,
    level: str | None = None,
    filename: str = "echo.log",
) -> None:
    """Configure root logger. Safe to call more than once (idempotent)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_dir = log_dir or os.environ.get("LOG_DIR", "./logs")
    level_name = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    level_value = getattr(logging, level_name, logging.INFO)

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logfile = Path(log_dir) / filename

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level_value)
    # Clear any pre-existing handlers (eg from libraries)
    root.handlers.clear()

    file_h = logging.handlers.RotatingFileHandler(
        str(logfile), maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_h.setFormatter(fmt)
    file_h.setLevel(level_value)
    root.addHandler(file_h)

    stream_h = logging.StreamHandler()
    stream_h.setFormatter(fmt)
    stream_h.setLevel(level_value)
    root.addHandler(stream_h)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(name)
