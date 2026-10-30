"""Executive KPI engine.

Computes the standard slate of sports-business KPIs that a Director of
Analytics would put in front of ownership/the front office. Every
function takes warehouse tables (already loaded as DataFrames) so it can
be reused by both the Streamlit dashboard and any reporting script
without re-querying the database on every call.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import pandas as pd

from analytics.db_utils import read_table
from etl.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class ExecutiveKPIs:
    total_revenue: float
    ticket_revenue: float
    merchandise_revenue: float
    total_tickets_sold: int
    avg_ticket_price: float
    avg_sell_through_rate: float
    avg_spend_per_fan: float
    repeat_purchase_rate_pct: float
    season_ticket_holder_pct: float
    revenue_per_match: float
    revenue_per_customer: float
    avg_campaign_roi_pct: float
    avg_customer_lifetime_value: float
    season_ticket_renewal_rate_pct: float


def _repeat_purchase_rate(ticket_sales: pd.DataFrame) -> float:
    games_per_customer = ticket_sales.groupby("CustomerID")["GameID"].nunique()
    repeat_buyers = (games_per_customer > 1).sum()
    return round(100 * repeat_buyers / len(games_per_customer), 2) if len(games_per_customer) else 0.0


def _season_ticket_renewal_rate(ticket_sales: pd.DataFrame, games: pd.DataFrame) -> float:
    # Select only the columns this function needs before merging: callers
    # (e.g. the dashboard) may pass in a ticket_sales frame that has already
    # been joined with games, and a naive merge here would collide on
    # "Season" and silently rename it to "Season_x"/"Season_y".
    base = ticket_sales[["CustomerID", "GameID", "TicketType"]]
    merged = base.merge(games[["GameID", "Season"]], on="GameID", how="left")
    seasons = sorted(merged["Season"].dropna().unique())
    if len(seasons) < 2:
        return 0.0
    s1, s2 = seasons[0], seasons[-1]
    s1_sth = set(merged[(merged["Season"] == s1) & (merged["TicketType"] == "Season")]["CustomerID"])
    s2_sth = set(merged[(merged["Season"] == s2) & (merged["TicketType"] == "Season")]["CustomerID"])
    if not s1_sth:
        return 0.0
    renewed = len(s1_sth & s2_sth)
    return round(100 * renewed / len(s1_sth), 2)


def _campaign_roi(ticket_sales: pd.DataFrame, campaigns: pd.DataFrame) -> float:
    attributed = ticket_sales.groupby("CampaignID")["Revenue"].sum()
    campaigns = campaigns.set_index("CampaignID")
    roi = ((attributed - campaigns["Cost"]) / campaigns["Cost"] * 100).dropna()
    return round(roi.mean(), 2) if len(roi) else 0.0


def compute_executive_kpis(
    ticket_sales: pd.DataFrame | None = None,
    games: pd.DataFrame | None = None,
    customers: pd.DataFrame | None = None,
    campaigns: pd.DataFrame | None = None,
    merchandise: pd.DataFrame | None = None,
) -> ExecutiveKPIs:
    """Compute the full executive KPI slate from warehouse tables."""
    ticket_sales = ticket_sales if ticket_sales is not None else read_table("ticket_sales")
    games = games if games is not None else read_table("games")
    customers = customers if customers is not None else read_table("customers")
    campaigns = campaigns if campaigns is not None else read_table("marketing_campaigns")
    merchandise = merchandise if merchandise is not None else read_table("merchandise")

    home_games = games[games["HomeAway"] == "Home"]
    ticket_revenue = ticket_sales["Revenue"].sum()
    merch_revenue = merchandise["AmountSpent"].sum()
    n_customers_with_purchase = ticket_sales["CustomerID"].nunique()

    kpis = ExecutiveKPIs(
        total_revenue=round(ticket_revenue + merch_revenue, 2),
        ticket_revenue=round(ticket_revenue, 2),
        merchandise_revenue=round(merch_revenue, 2),
        total_tickets_sold=int(len(ticket_sales)),
        avg_ticket_price=round(ticket_sales["PricePaid"].mean(), 2),
        avg_sell_through_rate=round(home_games["SellThroughRate"].mean(), 4),
        avg_spend_per_fan=round((ticket_revenue + merch_revenue) / n_customers_with_purchase, 2),
        repeat_purchase_rate_pct=_repeat_purchase_rate(ticket_sales),
        season_ticket_holder_pct=round(100 * customers["SeasonTicketHolder"].mean(), 2),
        revenue_per_match=round(ticket_revenue / home_games["GameID"].nunique(), 2),
        revenue_per_customer=round(ticket_revenue / n_customers_with_purchase, 2),
        avg_campaign_roi_pct=_campaign_roi(ticket_sales, campaigns),
        avg_customer_lifetime_value=round(customers.loc[customers["Frequency"] > 0, "LifetimeSpend"].mean(), 2),
        season_ticket_renewal_rate_pct=_season_ticket_renewal_rate(ticket_sales, games),
    )
    return kpis


def kpi_dataframe(kpis: ExecutiveKPIs) -> pd.DataFrame:
    """Present KPIs as a tidy label/value DataFrame for tables and dashboards."""
    labels = {
        "total_revenue": "Total Revenue ($)",
        "ticket_revenue": "Ticket Revenue ($)",
        "merchandise_revenue": "Merchandise Revenue ($)",
        "total_tickets_sold": "Total Tickets Sold",
        "avg_ticket_price": "Average Ticket Price ($)",
        "avg_sell_through_rate": "Average Sell-Through Rate",
        "avg_spend_per_fan": "Average Spend per Fan ($)",
        "repeat_purchase_rate_pct": "Repeat Purchase Rate (%)",
        "season_ticket_holder_pct": "Season Ticket Holder (%)",
        "revenue_per_match": "Revenue per Match ($)",
        "revenue_per_customer": "Revenue per Customer ($)",
        "avg_campaign_roi_pct": "Average Campaign ROI (%)",
        "avg_customer_lifetime_value": "Average Customer Lifetime Value ($)",
        "season_ticket_renewal_rate_pct": "Season Ticket Renewal Rate (%)",
    }
    data = asdict(kpis)
    return pd.DataFrame({"KPI": [labels[k] for k in data], "Value": list(data.values())})


if __name__ == "__main__":
    result = compute_executive_kpis()
    print(kpi_dataframe(result).to_string(index=False))
