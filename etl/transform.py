"""Transformation stage of the ETL pipeline.

Takes the cleaned CSVs and derives the analytics-ready feature set that
the database, SQL layer, and downstream analytics modules consume:
    - true customer LifetimeSpend recomputed from transactional history
    - RFM inputs (Recency, Frequency, Monetary) per customer
    - game-level derived flags (IsWeekend, IsHoliday, SellThroughRate)
    - ticket-level lead time and revenue-per-seat features

Writes the final processed CSVs to ``data/processed/``.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from config.config import load_config, resolve_path
from etl.clean import run_cleaning
from etl.logging_utils import get_logger

logger = get_logger(__name__)
CFG = load_config()

HOLIDAY_WINDOWS = [
    (11, 22, 29),
    (12, 20, 31),
    (1, 1, 2),
    (1, 15, 21),
    (2, 14, 17),
]


def _is_holiday(d: pd.Timestamp) -> bool:
    for month, start_day, end_day in HOLIDAY_WINDOWS:
        if d.month == month and start_day <= d.day <= end_day:
            return True
    return False


def transform_games(games: pd.DataFrame) -> pd.DataFrame:
    """Add calendar and demand-related derived fields to the schedule."""
    df = games.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df["IsWeekend"] = df["Date"].dt.day_name().isin(["Saturday", "Sunday"])
    df["IsHoliday"] = df["Date"].apply(_is_holiday)
    df["Month"] = df["Date"].dt.month
    df["Year"] = df["Date"].dt.year
    df["SellThroughRate"] = np.where(
        df["HomeAway"] == "Home", df["Attendance"] / df["Capacity"].replace(0, np.nan), np.nan
    )
    df["IsRivalGame"] = df["Opponent"].isin(CFG["schedule"]["rival_opponents"])
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    return df


def transform_ticket_sales(ticket_sales: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Add purchase lead time and normalize monetary rounding."""
    df = ticket_sales.copy()
    game_dates = games.set_index("GameID")["Date"]
    df["GameDate"] = pd.to_datetime(df["GameID"].map(game_dates))
    df["PurchaseDate"] = pd.to_datetime(df["PurchaseDate"])

    # Purchases logged after the game date are a clock/entry error; clamp
    # them back to the game date so lead time is never negative.
    after_game = df["PurchaseDate"] > df["GameDate"]
    if after_game.any():
        logger.warning("ticket_sales: clamping %d post-game purchase dates", after_game.sum())
        df.loc[after_game, "PurchaseDate"] = df.loc[after_game, "GameDate"]

    df["PurchaseLeadTimeDays"] = (df["GameDate"] - df["PurchaseDate"]).dt.days
    df["PurchaseMonth"] = df["PurchaseDate"].dt.to_period("M").astype(str)
    df["PurchaseDate"] = df["PurchaseDate"].dt.strftime("%Y-%m-%d")
    df["GameDate"] = df["GameDate"].dt.strftime("%Y-%m-%d")
    for col in ("PricePaid", "Discount", "Fees", "Revenue"):
        df[col] = df[col].round(2)
    return df


def compute_rfm(ticket_sales: pd.DataFrame, merchandise: pd.DataFrame, as_of: date | None = None) -> pd.DataFrame:
    """Compute Recency (days), Frequency (orders), Monetary (spend) per customer."""
    as_of_ts = pd.Timestamp(as_of) if as_of else pd.to_datetime(ticket_sales["PurchaseDate"]).max()

    ticket_spend = ticket_sales.groupby("CustomerID").agg(
        Frequency=("TicketID", "count"),
        TicketRevenue=("Revenue", "sum"),
        LastPurchaseDate=("PurchaseDate", "max"),
    )
    merch_spend = merchandise.groupby("CustomerID")["AmountSpent"].sum().rename("MerchRevenue")

    rfm = ticket_spend.join(merch_spend, how="left").fillna({"MerchRevenue": 0.0})
    rfm["Monetary"] = (rfm["TicketRevenue"] + rfm["MerchRevenue"]).round(2)
    rfm["LastPurchaseDate"] = pd.to_datetime(rfm["LastPurchaseDate"])
    rfm["Recency"] = (as_of_ts - rfm["LastPurchaseDate"]).dt.days
    rfm = rfm.reset_index()[["CustomerID", "Recency", "Frequency", "Monetary"]]
    return rfm


def transform_customers(customers: pd.DataFrame, ticket_sales: pd.DataFrame, merchandise: pd.DataFrame) -> pd.DataFrame:
    """Recompute true LifetimeSpend and attach RFM inputs to the customer master."""
    df = customers.copy().rename(columns={"LifetimeSpend": "CrmReportedLifetimeSpend"})
    rfm = compute_rfm(ticket_sales, merchandise)

    df = df.merge(rfm, on="CustomerID", how="left")
    df["Frequency"] = df["Frequency"].fillna(0).astype(int)
    df["Monetary"] = df["Monetary"].fillna(0.0)
    df.rename(columns={"Monetary": "LifetimeSpend"}, inplace=True)
    df["Recency"] = df["Recency"].fillna(-1).astype(int)  # -1 = never purchased

    df["SignupDate"] = pd.to_datetime(df["SignupDate"])
    df["TenureDays"] = (pd.Timestamp(df["SignupDate"].max()) - df["SignupDate"]).dt.days
    df["SignupDate"] = df["SignupDate"].dt.strftime("%Y-%m-%d")

    df["AgeGroup"] = pd.cut(
        df["Age"], bins=[0, 17, 24, 34, 44, 54, 64, 120],
        labels=["Under 18", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"],
    )

    spend_gap = (df["LifetimeSpend"] - df["CrmReportedLifetimeSpend"]).abs()
    logger.info(
        "customers: recomputed LifetimeSpend from transactions (avg CRM drift $%.2f)",
        spend_gap.mean(),
    )
    return df


def run_transformation() -> dict[str, pd.DataFrame]:
    """Execute the full transformation stage and persist processed CSVs."""
    logger.info("Starting transformation stage")
    cleaned = run_cleaning()

    games = transform_games(cleaned["games"])
    ticket_sales = transform_ticket_sales(cleaned["ticket_sales"], games)
    customers = transform_customers(cleaned["customers"], ticket_sales, cleaned["merchandise"])
    campaigns = cleaned["campaigns"]
    merchandise = cleaned["merchandise"]

    processed_dir = resolve_path(CFG["paths"]["processed_dir"])
    processed_dir.mkdir(parents=True, exist_ok=True)
    customers.to_csv(processed_dir / "customers.csv", index=False)
    campaigns.to_csv(processed_dir / "marketing_campaigns.csv", index=False)
    games.to_csv(processed_dir / "games.csv", index=False)
    ticket_sales.to_csv(processed_dir / "ticket_sales.csv", index=False)
    merchandise.to_csv(processed_dir / "merchandise.csv", index=False)

    logger.info("Transformation stage complete. Processed data written to %s", processed_dir)
    return {
        "customers": customers,
        "campaigns": campaigns,
        "games": games,
        "ticket_sales": ticket_sales,
        "merchandise": merchandise,
    }


if __name__ == "__main__":
    run_transformation()
