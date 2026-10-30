"""Orchestrates the full ETL pipeline: generate -> validate -> clean -> transform -> load.

Usage:
    python -m etl.run_pipeline [--skip-generate]
"""
from __future__ import annotations

import argparse

from etl.generate_data import main as generate_data
from etl.load_database import load_database
from etl.logging_utils import get_logger
from etl.validate import run_validation

logger = get_logger(__name__)


def run(skip_generate: bool = False) -> None:
    if not skip_generate:
        logger.info("=== STAGE 1/4: GENERATE ===")
        generate_data()
    else:
        logger.info("=== STAGE 1/4: GENERATE (skipped) ===")

    logger.info("=== STAGE 2/4: VALIDATE ===")
    run_validation()

    logger.info("=== STAGE 3/4 + 4/4: CLEAN -> TRANSFORM -> LOAD ===")
    load_database()

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Sports BI ETL pipeline")
    parser.add_argument("--skip-generate", action="store_true", help="Reuse existing raw CSVs")
    args = parser.parse_args()
    run(skip_generate=args.skip_generate)
