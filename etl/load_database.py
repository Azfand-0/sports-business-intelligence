"""Load stage of the ETL pipeline.

Creates (or recreates) the SQLite warehouse from the SQLAlchemy models in
``etl/models.py`` and bulk-loads the processed CSVs produced by
``etl/transform.py``.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine

from config.config import load_config, resolve_path
from etl.logging_utils import get_logger
from etl.models import Base
from etl.transform import run_transformation

logger = get_logger(__name__)
CFG = load_config()

TABLE_ORDER = ["customers", "marketing_campaigns", "games", "ticket_sales", "merchandise"]


def get_engine():
    """Create the SQLAlchemy engine pointed at database/ticket_sales.db."""
    db_path = resolve_path(CFG["paths"]["database"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}")


def load_database(data: dict[str, pd.DataFrame] | None = None) -> None:
    """Create schema and bulk-load all tables in FK-safe order."""
    logger.info("Starting load stage")
    engine = get_engine()

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    logger.info("Schema created at %s", engine.url)

    data = data or run_transformation()

    table_map = {
        "customers": data["customers"],
        "marketing_campaigns": data["campaigns"],
        "games": data["games"],
        "ticket_sales": data["ticket_sales"],
        "merchandise": data["merchandise"],
    }

    with engine.begin() as conn:
        for table_name in TABLE_ORDER:
            df = table_map[table_name]
            df.to_sql(table_name, conn, if_exists="append", index=False)
            logger.info("Loaded %d rows into %s", len(df), table_name)

    logger.info("Load stage complete")


if __name__ == "__main__":
    load_database()
