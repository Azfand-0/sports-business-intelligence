"""Configuration loader for the Sports Business Intelligence Platform.

All pipeline stages (ETL, analytics, dashboard) read shared constants from
``config/config.yaml`` through this module so that business assumptions
(stadium capacity, seat pricing, season dates, etc.) live in exactly one
place.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    """Load and cache the project configuration file.

    Returns:
        Parsed YAML configuration as a nested dictionary.
    """
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def resolve_path(relative_path: str) -> Path:
    """Resolve a path from ``config.yaml`` relative to the project root."""
    return PROJECT_ROOT / relative_path
