"""Shared logging configuration for all ETL stages."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from config.config import resolve_path


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger that writes to console and a log file.

    Args:
        name: Usually ``__name__`` of the calling module.

    Returns:
        A configured ``logging.Logger`` instance.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # avoid duplicate handlers on repeated calls

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    logs_dir = resolve_path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(logs_dir / "pipeline.log")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger
