"""Shared helper for analytics modules to read from the SQLite warehouse."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from config.config import load_config, resolve_path

CFG = load_config()


def get_engine() -> Engine:
    db_path = resolve_path(CFG["paths"]["database"])
    return create_engine(f"sqlite:///{db_path}")


def read_table(table_name: str) -> pd.DataFrame:
    """Read a full table from the warehouse into a DataFrame."""
    return pd.read_sql_table(table_name, get_engine())


def read_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Run an arbitrary SQL query against the warehouse."""
    return pd.read_sql_query(sql, get_engine(), params=params)
