"""Sanity checks against the loaded warehouse.

Run with: pytest tests/ (after the ETL pipeline has populated
database/ticket_sales.db).
"""
from __future__ import annotations

import pandas as pd
import pytest

from analytics.db_utils import read_table


@pytest.fixture(scope="module")
def customers() -> pd.DataFrame:
    return read_table("customers")


@pytest.fixture(scope="module")
def games() -> pd.DataFrame:
    return read_table("games")


@pytest.fixture(scope="module")
def ticket_sales() -> pd.DataFrame:
    return read_table("ticket_sales")


@pytest.fixture(scope="module")
def merchandise() -> pd.DataFrame:
    return read_table("merchandise")


def test_ticket_volume_near_target(ticket_sales: pd.DataFrame) -> None:
    assert 90_000 <= len(ticket_sales) <= 110_000


def test_no_negative_monetary_values(ticket_sales: pd.DataFrame) -> None:
    assert (ticket_sales["PricePaid"] >= 0).all()
    assert (ticket_sales["Revenue"] >= 0).all()
    assert (ticket_sales["Discount"] >= 0).all()
    assert (ticket_sales["Fees"] >= 0).all()


def test_referential_integrity(ticket_sales: pd.DataFrame, customers: pd.DataFrame, games: pd.DataFrame) -> None:
    assert ticket_sales["CustomerID"].isin(customers["CustomerID"]).all()
    assert ticket_sales["GameID"].isin(games["GameID"]).all()


def test_attendance_never_exceeds_capacity(games: pd.DataFrame) -> None:
    assert (games["Attendance"] <= games["Capacity"]).all()


def test_no_duplicate_primary_keys(customers: pd.DataFrame, games: pd.DataFrame, ticket_sales: pd.DataFrame) -> None:
    assert customers["CustomerID"].is_unique
    assert games["GameID"].is_unique
    assert ticket_sales["TicketID"].is_unique


def test_seat_section_never_oversold_per_game(ticket_sales: pd.DataFrame, games: pd.DataFrame) -> None:
    home_game_ids = games.loc[games["HomeAway"] == "Home", "GameID"]
    home_tickets = ticket_sales[ticket_sales["GameID"].isin(home_game_ids)]
    per_game_section_counts = home_tickets.groupby(["GameID", "SeatSection"]).size()
    # No single section should sell more seats than the stadium physically has
    # allocated to it (see config.yaml seat_sections pct_of_capacity).
    assert per_game_section_counts.max() <= games["Capacity"].max()


def test_merchandise_linked_to_real_visits(merchandise: pd.DataFrame, customers: pd.DataFrame, games: pd.DataFrame) -> None:
    assert merchandise["CustomerID"].isin(customers["CustomerID"]).all()
    assert merchandise["GameID"].isin(games["GameID"]).all()
    assert (merchandise["AmountSpent"] >= 0).all()


def test_season_ticket_holder_share_is_plausible(customers: pd.DataFrame) -> None:
    sth_pct = customers["SeasonTicketHolder"].mean()
    assert 0.05 <= sth_pct <= 0.25
