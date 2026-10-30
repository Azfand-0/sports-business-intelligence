"""Validation stage of the ETL pipeline.

Runs read-only data quality checks against the raw CSV extracts and
produces a human-readable data quality report. Nothing is mutated here;
``clean.py`` is responsible for fixing the issues this stage surfaces.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pandas as pd

from config.config import load_config, resolve_path
from etl.logging_utils import get_logger

logger = get_logger(__name__)
CFG = load_config()
ZIP_PATTERN = re.compile(r"^\d{5}$")


def _load_raw() -> dict[str, pd.DataFrame]:
    raw_dir = resolve_path(CFG["paths"]["raw_dir"])
    return {
        "customers": pd.read_csv(raw_dir / "customers.csv", dtype={"ZipCode": str}),
        "campaigns": pd.read_csv(raw_dir / "marketing_campaigns.csv"),
        "games": pd.read_csv(raw_dir / "games.csv"),
        "ticket_sales": pd.read_csv(raw_dir / "ticket_sales.csv"),
        "merchandise": pd.read_csv(raw_dir / "merchandise.csv"),
    }


def check_missing_values(df: pd.DataFrame, table_name: str) -> dict[str, int]:
    """Return a column -> missing-count mapping for a table."""
    missing = df.isna().sum()
    missing = missing[missing > 0].to_dict()
    if missing:
        logger.warning("[%s] missing values: %s", table_name, missing)
    return {str(k): int(v) for k, v in missing.items()}


def check_duplicates(df: pd.DataFrame, table_name: str, subset: list[str] | None = None) -> int:
    """Return the count of duplicate rows (optionally on a column subset)."""
    n_dupes = int(df.duplicated(subset=subset).sum())
    if n_dupes:
        logger.warning("[%s] duplicate rows: %d", table_name, n_dupes)
    return n_dupes


def check_referential_integrity(ticket_sales: pd.DataFrame, customers: pd.DataFrame,
                                  games: pd.DataFrame, campaigns: pd.DataFrame) -> dict[str, int]:
    """Verify every foreign key in ticket_sales resolves to a parent row."""
    orphan_customers = int((~ticket_sales["CustomerID"].isin(customers["CustomerID"])).sum())
    orphan_games = int((~ticket_sales["GameID"].isin(games["GameID"])).sum())
    has_campaign = ticket_sales["CampaignID"].notna()
    orphan_campaigns = int((has_campaign & ~ticket_sales.loc[has_campaign, "CampaignID"].isin(campaigns["CampaignID"])).sum())

    result = {
        "orphan_customer_fk": orphan_customers,
        "orphan_game_fk": orphan_games,
        "orphan_campaign_fk": orphan_campaigns,
    }
    for key, count in result.items():
        if count:
            logger.warning("Referential integrity violation - %s: %d rows", key, count)
    return result


def check_zip_codes(customers: pd.DataFrame) -> int:
    """Count malformed (non 5-digit) ZIP codes."""
    zips = customers["ZipCode"].fillna("").astype(str)
    invalid = zips.apply(lambda z: ZIP_PATTERN.match(z) is None).sum()
    if invalid:
        logger.warning("Malformed ZIP codes: %d", invalid)
    return int(invalid)


def check_negative_prices(ticket_sales: pd.DataFrame) -> dict[str, int]:
    """Count rows with negative monetary values that should never be negative."""
    result = {
        "negative_price_paid": int((ticket_sales["PricePaid"] < 0).sum()),
        "negative_revenue": int((ticket_sales["Revenue"] < 0).sum()),
    }
    for key, count in result.items():
        if count:
            logger.warning("%s: %d rows", key, count)
    return result


def check_date_logic(ticket_sales: pd.DataFrame, games: pd.DataFrame) -> int:
    """Count tickets purchased strictly after the game they belong to."""
    merged = ticket_sales.merge(games[["GameID", "Date"]], on="GameID", how="left", suffixes=("", "_game"))
    purchase = pd.to_datetime(merged["PurchaseDate"], errors="coerce")
    game_date = pd.to_datetime(merged["Date"], errors="coerce")
    bad = int((purchase > game_date).sum())
    if bad:
        logger.warning("Tickets purchased after their game date: %d", bad)
    return bad


def check_mixed_date_formats(games: pd.DataFrame) -> int:
    """Count game dates that are not already in ISO (YYYY-MM-DD) format."""
    iso_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    non_iso = games["Date"].astype(str).apply(lambda d: iso_pattern.match(d) is None).sum()
    if non_iso:
        logger.warning("Non-ISO date formats in games.Date: %d", non_iso)
    return int(non_iso)


def run_validation() -> dict[str, Any]:
    """Execute the full validation suite and write a markdown report."""
    logger.info("Starting validation stage")
    data = _load_raw()

    report: dict[str, Any] = {"generated_at": datetime.now().isoformat()}
    report["missing_values"] = {name: check_missing_values(df, name) for name, df in data.items()}
    report["duplicates"] = {name: check_duplicates(df, name) for name, df in data.items()}
    report["referential_integrity"] = check_referential_integrity(
        data["ticket_sales"], data["customers"], data["games"], data["campaigns"]
    )
    report["malformed_zip_codes"] = check_zip_codes(data["customers"])
    report["negative_prices"] = check_negative_prices(data["ticket_sales"])
    report["purchase_after_game_date"] = check_date_logic(data["ticket_sales"], data["games"])
    report["non_iso_game_dates"] = check_mixed_date_formats(data["games"])

    _write_report(report)
    logger.info("Validation stage complete")
    return report


def _write_report(report: dict[str, Any]) -> None:
    reports_dir = resolve_path(CFG["paths"]["reports_dir"])
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / "data_quality_report.md"

    lines = ["# Data Quality Report", "", f"Generated: {report['generated_at']}", ""]
    lines.append("## Missing Values")
    for table, cols in report["missing_values"].items():
        lines.append(f"- **{table}**: {cols if cols else 'none'}")
    lines.append("\n## Duplicate Rows")
    for table, count in report["duplicates"].items():
        lines.append(f"- **{table}**: {count}")
    lines.append("\n## Referential Integrity")
    for key, count in report["referential_integrity"].items():
        lines.append(f"- **{key}**: {count}")
    lines.append(f"\n## Malformed ZIP Codes\n- {report['malformed_zip_codes']}")
    lines.append("\n## Negative Prices")
    for key, count in report["negative_prices"].items():
        lines.append(f"- **{key}**: {count}")
    lines.append(f"\n## Purchases After Game Date\n- {report['purchase_after_game_date']}")
    lines.append(f"\n## Non-ISO Game Dates\n- {report['non_iso_game_dates']}")

    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Data quality report written to %s", path)


if __name__ == "__main__":
    run_validation()
