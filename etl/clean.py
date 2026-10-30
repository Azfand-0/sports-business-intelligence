"""Cleaning stage of the ETL pipeline.

Fixes the data quality issues surfaced by ``validate.py``:
    - de-duplication
    - missing value handling
    - text standardization (casing)
    - date parsing to ISO 8601
    - ZIP code validation
    - price sign correction / outlier flags
    - referential integrity enforcement

Writes cleaned CSVs to ``data/cleaned/``.
"""
from __future__ import annotations

import re

import numpy as np
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


def _parse_mixed_date(value: str) -> str | float:
    """Parse a date that may be ISO, US-slash, or long-form and return ISO."""
    if pd.isna(value):
        return np.nan
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y"):
        try:
            return pd.to_datetime(value, format=fmt).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    return np.nan


def clean_customers(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize and de-duplicate the customer master file."""
    before = len(df)
    df = df.drop_duplicates(subset=["FirstName", "LastName", "Email", "SignupDate"]).copy()
    logger.info("customers: removed %d exact/near duplicate rows", before - len(df))

    df["City"] = df["City"].str.strip().str.title()
    df["State"] = df["State"].str.strip().str.upper()

    # ZIP validation: null out anything that isn't a clean 5-digit code
    zip_str = df["ZipCode"].fillna("").astype(str)
    invalid_zip = ~zip_str.apply(lambda z: bool(ZIP_PATTERN.match(z)))
    logger.info("customers: nulling %d malformed ZIP codes", invalid_zip.sum())
    df.loc[invalid_zip, "ZipCode"] = np.nan

    # Missing Age -> impute with segment median (outlier-robust)
    df["Age"] = df.groupby("CustomerSegment")["Age"].transform(lambda s: s.fillna(s.median()))
    df["Age"] = df["Age"].fillna(df["Age"].median()).astype(int)

    # Outlier detection on Age (clip to plausible fan age range)
    n_outliers = int(((df["Age"] < 5) | (df["Age"] > 100)).sum())
    if n_outliers:
        logger.warning("customers: clipping %d implausible ages", n_outliers)
    df["Age"] = df["Age"].clip(5, 100)

    df["PreferredSeatSection"] = df["PreferredSeatSection"].fillna("Lower Bowl")
    df["Email"] = df["Email"].fillna("unknown@meridiancityfc.example")
    df["SignupDate"] = pd.to_datetime(df["SignupDate"]).dt.strftime("%Y-%m-%d")
    df["SeasonTicketHolder"] = df["SeasonTicketHolder"].astype(bool)

    return df.reset_index(drop=True)


def clean_campaigns(df: pd.DataFrame) -> pd.DataFrame:
    """Campaigns are generated clean; still enforce dtypes defensively."""
    df = df.drop_duplicates(subset=["CampaignID"]).copy()
    df["StartDate"] = pd.to_datetime(df["StartDate"]).dt.strftime("%Y-%m-%d")
    df["EndDate"] = pd.to_datetime(df["EndDate"]).dt.strftime("%Y-%m-%d")
    return df.reset_index(drop=True)


def clean_games(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize game schedule fields."""
    df = df.drop_duplicates(subset=["GameID"]).copy()

    df["Date"] = df["Date"].apply(_parse_mixed_date)
    n_bad_dates = df["Date"].isna().sum()
    if n_bad_dates:
        logger.warning("games: %d rows had unparseable dates, dropping", n_bad_dates)
        df = df.dropna(subset=["Date"])

    for col in ("Weather", "DayOfWeek", "Competition", "HomeAway"):
        df[col] = df[col].astype(str).str.strip().str.title()
        df.loc[df[col].isin(["Nan", "None"]), col] = np.nan

    df["Weather"] = df["Weather"].fillna("Unknown")
    df["Temperature"] = df.groupby("Weather")["Temperature"].transform(lambda s: s.fillna(s.median()))
    df["Temperature"] = df["Temperature"].fillna(df["Temperature"].median())

    df["PromotionNight"] = df["PromotionNight"].astype(bool)
    df["Capacity"] = df["Capacity"].astype(int)
    df["Attendance"] = df["Attendance"].clip(lower=0)
    # Attendance can never exceed capacity (data entry sanity check)
    over_capacity = (df["Attendance"] > df["Capacity"]).sum()
    if over_capacity:
        logger.warning("games: %d rows had attendance over capacity, clipping", over_capacity)
    df["Attendance"] = np.minimum(df["Attendance"], df["Capacity"])

    return df.reset_index(drop=True)


def clean_ticket_sales(df: pd.DataFrame, valid_customer_ids: set, valid_game_ids: set,
                        valid_campaign_ids: set) -> pd.DataFrame:
    """Fix pricing, dates, casing, and referential integrity on the fact table."""
    before = len(df)
    df = df.drop_duplicates(subset=["TicketID"]).copy()
    logger.info("ticket_sales: removed %d duplicate rows", before - len(df))

    # Referential integrity: drop orphaned foreign keys
    before = len(df)
    df = df[df["CustomerID"].isin(valid_customer_ids)]
    df = df[df["GameID"].isin(valid_game_ids)]
    logger.info("ticket_sales: dropped %d rows with broken customer/game FKs", before - len(df))

    valid_campaign_mask = df["CampaignID"].isna() | df["CampaignID"].isin(valid_campaign_ids)
    dropped_campaigns = (~valid_campaign_mask).sum()
    if dropped_campaigns:
        logger.warning("ticket_sales: nulling %d invalid campaign references", dropped_campaigns)
    df.loc[~valid_campaign_mask, "CampaignID"] = np.nan

    for col in ("PurchaseChannel", "TicketType", "SeatSection", "PaymentMethod"):
        df[col] = df[col].astype(str).str.strip().str.title()
        df.loc[df[col].isin(["Nan", "None"]), col] = np.nan

    df["PaymentMethod"] = df["PaymentMethod"].fillna("Unknown")
    df["Discount"] = df["Discount"].fillna(0.0)
    df["Fees"] = df["Fees"].fillna(0.0)

    # Negative price correction: these are sign-flip data entry errors
    n_negative = int((df["PricePaid"] < 0).sum())
    if n_negative:
        logger.warning("ticket_sales: correcting sign on %d negative PricePaid values", n_negative)
    df["PricePaid"] = df["PricePaid"].abs()
    df["Revenue"] = df["Revenue"].abs()

    df["PurchaseDate"] = pd.to_datetime(df["PurchaseDate"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["Scanned"] = df["Scanned"].astype(bool)
    df["Attended"] = df["Attended"].astype(bool)

    return df.reset_index(drop=True)


def clean_merchandise(df: pd.DataFrame, valid_customer_ids: set, valid_game_ids: set) -> pd.DataFrame:
    """De-duplicate and enforce referential integrity on merchandise sales."""
    before = len(df)
    df = df.drop_duplicates().copy()
    df = df[df["CustomerID"].isin(valid_customer_ids)]
    df = df[df["GameID"].isin(valid_game_ids)]
    df["AmountSpent"] = df["AmountSpent"].clip(lower=0)
    logger.info("merchandise: removed %d duplicate/orphaned rows", before - len(df))
    return df.reset_index(drop=True)


def run_cleaning() -> dict[str, pd.DataFrame]:
    """Execute the full cleaning stage and persist cleaned CSVs."""
    logger.info("Starting cleaning stage")
    data = _load_raw()

    customers = clean_customers(data["customers"])
    campaigns = clean_campaigns(data["campaigns"])
    games = clean_games(data["games"])
    ticket_sales = clean_ticket_sales(
        data["ticket_sales"],
        set(customers["CustomerID"]),
        set(games["GameID"]),
        set(campaigns["CampaignID"]),
    )
    merchandise = clean_merchandise(data["merchandise"], set(customers["CustomerID"]), set(games["GameID"]))

    cleaned_dir = resolve_path(CFG["paths"]["cleaned_dir"])
    cleaned_dir.mkdir(parents=True, exist_ok=True)
    customers.to_csv(cleaned_dir / "customers.csv", index=False)
    campaigns.to_csv(cleaned_dir / "marketing_campaigns.csv", index=False)
    games.to_csv(cleaned_dir / "games.csv", index=False)
    ticket_sales.to_csv(cleaned_dir / "ticket_sales.csv", index=False)
    merchandise.to_csv(cleaned_dir / "merchandise.csv", index=False)

    logger.info("Cleaning stage complete. Cleaned data written to %s", cleaned_dir)
    return {
        "customers": customers,
        "campaigns": campaigns,
        "games": games,
        "ticket_sales": ticket_sales,
        "merchandise": merchandise,
    }


if __name__ == "__main__":
    run_cleaning()
