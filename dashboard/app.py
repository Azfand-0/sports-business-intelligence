"""Meridian City FC — Sports Business Intelligence Dashboard.

A Streamlit application mirroring what a BI Data Analyst would ship for a
professional sports franchise's front office: an executive KPI overview,
revenue/attendance/customer/campaign deep dives, an ML forecasting page,
and a live SQL explorer against the warehouse.

Run with:  streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.db_utils import get_engine, read_table
from analytics.forecasting import run_forecasting
from analytics.kpi_calculations import compute_executive_kpis, kpi_dataframe
from analytics.segmentation import run_segmentation
from config.config import load_config

CFG = load_config()
CLUB_NAME = CFG["club"]["name"]

st.set_page_config(page_title=f"{CLUB_NAME} BI Platform", page_icon="⚽", layout="wide")


# --------------------------------------------------------------------------- #
# Cached data access
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner="Loading warehouse tables...")
def load_data() -> dict[str, pd.DataFrame]:
    customers = read_table("customers")
    games = read_table("games")
    ticket_sales = read_table("ticket_sales")
    campaigns = read_table("marketing_campaigns")
    merchandise = read_table("merchandise")

    ticket_sales["PurchaseDate"] = pd.to_datetime(ticket_sales["PurchaseDate"])
    games["Date"] = pd.to_datetime(games["Date"])
    return {
        "customers": customers,
        "games": games,
        "ticket_sales": ticket_sales,
        "campaigns": campaigns,
        "merchandise": merchandise,
    }


@st.cache_data(show_spinner="Computing RFM segments...")
def load_segments() -> tuple[pd.DataFrame, pd.DataFrame]:
    return run_segmentation(persist=False)


@st.cache_data(show_spinner="Training forecasting models...")
def load_forecasts() -> dict:
    return run_forecasting(persist=False)


def build_fact_table(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Join ticket_sales with games, customers, and campaigns for filtering."""
    fact = data["ticket_sales"].merge(
        data["games"][["GameID", "Season", "Date", "Opponent", "Competition", "HomeAway",
                       "Weather", "PromotionNight", "IsWeekend", "IsHoliday", "IsRivalGame",
                       "Attendance", "Capacity", "SellThroughRate"]],
        on="GameID", how="left",
    )
    fact = fact.merge(
        data["customers"][["CustomerID", "CustomerSegment", "State", "ZipCode", "Age", "AgeGroup", "SeasonTicketHolder"]],
        on="CustomerID", how="left",
    )
    fact = fact.merge(
        data["campaigns"][["CampaignID", "CampaignName", "CampaignType"]],
        on="CampaignID", how="left",
    )
    return fact


# --------------------------------------------------------------------------- #
# Sidebar filters
# --------------------------------------------------------------------------- #
def render_filters(fact: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filters")

    min_date, max_date = fact["PurchaseDate"].min().date(), fact["PurchaseDate"].max().date()
    date_range = st.sidebar.date_input("Purchase date range", value=(min_date, max_date),
                                        min_value=min_date, max_value=max_date)
    opponents = st.sidebar.multiselect("Opponent", sorted(fact["Opponent"].dropna().unique()))
    sections = st.sidebar.multiselect("Seat section", sorted(fact["SeatSection"].dropna().unique()))
    ticket_types = st.sidebar.multiselect("Ticket type", sorted(fact["TicketType"].dropna().unique()))
    camp_names = st.sidebar.multiselect("Campaign", sorted(fact["CampaignName"].dropna().unique()))
    segments = st.sidebar.multiselect("Customer segment (CRM)", sorted(fact["CustomerSegment"].dropna().unique()))

    filtered = fact.copy()
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        filtered = filtered[(filtered["PurchaseDate"].dt.date >= start) & (filtered["PurchaseDate"].dt.date <= end)]
    if opponents:
        filtered = filtered[filtered["Opponent"].isin(opponents)]
    if sections:
        filtered = filtered[filtered["SeatSection"].isin(sections)]
    if ticket_types:
        filtered = filtered[filtered["TicketType"].isin(ticket_types)]
    if camp_names:
        filtered = filtered[filtered["CampaignName"].isin(camp_names)]
    if segments:
        filtered = filtered[filtered["CustomerSegment"].isin(segments)]

    st.sidebar.caption(f"{len(filtered):,} of {len(fact):,} ticket line items match current filters")
    return filtered


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
def page_executive_overview(data: dict, fact: pd.DataFrame) -> None:
    st.title(f"{CLUB_NAME} — Executive Overview")
    st.caption("Union Field | Two-season ticketing, CRM, and marketing performance snapshot")

    kpis = compute_executive_kpis(
        ticket_sales=fact if len(fact) else data["ticket_sales"],
        games=data["games"], customers=data["customers"],
        campaigns=data["campaigns"], merchandise=data["merchandise"],
    )

    cols = st.columns(4)
    cols[0].metric("Total Revenue", f"${kpis.total_revenue:,.0f}")
    cols[1].metric("Avg Sell-Through Rate", f"{kpis.avg_sell_through_rate:.1%}")
    cols[2].metric("Avg Ticket Price", f"${kpis.avg_ticket_price:,.2f}")
    cols[3].metric("Season Ticket Renewal", f"{kpis.season_ticket_renewal_rate_pct:.1f}%")

    cols2 = st.columns(4)
    cols2[0].metric("Repeat Purchase Rate", f"{kpis.repeat_purchase_rate_pct:.1f}%")
    cols2[1].metric("Season Ticket Holders", f"{kpis.season_ticket_holder_pct:.1f}%")
    cols2[2].metric("Avg Customer LTV", f"${kpis.avg_customer_lifetime_value:,.2f}")
    cols2[3].metric("Avg Campaign ROI", f"{kpis.avg_campaign_roi_pct:,.1f}%")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        monthly = fact.groupby(fact["PurchaseDate"].dt.to_period("M").astype(str))["Revenue"].sum().reset_index()
        monthly.columns = ["Month", "Revenue"]
        st.plotly_chart(px.line(monthly, x="Month", y="Revenue", markers=True, title="Revenue Trend"),
                         use_container_width=True)
    with c2:
        home = data["games"][data["games"]["HomeAway"] == "Home"]
        att = home.groupby(home["Date"].dt.to_period("M").astype(str))["Attendance"].mean().reset_index()
        att.columns = ["Month", "AvgAttendance"]
        st.plotly_chart(px.bar(att, x="Month", y="AvgAttendance", title="Average Attendance by Month"),
                         use_container_width=True)

    st.subheader("Full KPI Table")
    st.dataframe(kpi_dataframe(kpis), use_container_width=True, hide_index=True)


def page_revenue(fact: pd.DataFrame) -> None:
    st.title("Revenue")
    if fact.empty:
        st.warning("No data matches the current filters.")
        return

    c1, c2 = st.columns(2)
    with c1:
        by_section = fact.groupby("SeatSection")["Revenue"].sum().sort_values(ascending=False).reset_index()
        st.plotly_chart(px.bar(by_section, x="SeatSection", y="Revenue", title="Revenue by Seat Section"),
                         use_container_width=True)
    with c2:
        by_type = fact.groupby("TicketType")["Revenue"].sum().sort_values(ascending=False).reset_index()
        st.plotly_chart(px.bar(by_type, x="TicketType", y="Revenue", title="Revenue by Ticket Type"),
                         use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        by_channel = fact.groupby("PurchaseChannel")["Revenue"].sum().sort_values(ascending=False).reset_index()
        st.plotly_chart(px.pie(by_channel, names="PurchaseChannel", values="Revenue", title="Revenue by Purchase Channel"),
                         use_container_width=True)
    with c4:
        by_payment = fact.groupby("PaymentMethod")["Revenue"].sum().sort_values(ascending=False).reset_index()
        st.plotly_chart(px.bar(by_payment, x="PaymentMethod", y="Revenue", title="Revenue by Payment Method"),
                         use_container_width=True)

    st.subheader("Top 25 Customers by Revenue (current filters)")
    top_customers = fact.groupby(["CustomerID"]).agg(
        Tickets=("TicketID", "count"), Revenue=("Revenue", "sum")
    ).sort_values("Revenue", ascending=False).head(25).reset_index()
    st.dataframe(top_customers, use_container_width=True, hide_index=True)


def page_attendance(data: dict, fact: pd.DataFrame) -> None:
    st.title("Attendance")
    home_games = data["games"][data["games"]["HomeAway"] == "Home"].copy()
    if not fact.empty:
        home_games = home_games[home_games["GameID"].isin(fact["GameID"])]

    c1, c2 = st.columns(2)
    with c1:
        weekday = home_games.groupby("DayOfWeek")["Attendance"].mean().reset_index()
        st.plotly_chart(px.bar(weekday, x="DayOfWeek", y="Attendance", title="Average Attendance by Day of Week"),
                         use_container_width=True)
    with c2:
        weather = home_games.groupby("Weather")["Attendance"].mean().reset_index()
        st.plotly_chart(px.bar(weather, x="Weather", y="Attendance", title="Average Attendance by Weather"),
                         use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        promo = home_games.copy()
        promo["PromotionNight"] = promo["PromotionNight"].map({True: "Promotion Night", False: "Standard Night", 1: "Promotion Night", 0: "Standard Night"})
        promo_summary = promo.groupby("PromotionNight")["Attendance"].mean().reset_index()
        st.plotly_chart(px.bar(promo_summary, x="PromotionNight", y="Attendance", title="Promotion Night Effect"),
                         use_container_width=True)
    with c4:
        rival = home_games.copy()
        rival["IsRivalGame"] = rival["IsRivalGame"].map({True: "Rival", False: "Non-Rival", 1: "Rival", 0: "Non-Rival"})
        rival_summary = rival.groupby("IsRivalGame")["Attendance"].mean().reset_index()
        st.plotly_chart(px.bar(rival_summary, x="IsRivalGame", y="Attendance", title="Rival Game Effect"),
                         use_container_width=True)

    st.subheader("Sell-Through Rate by Game")
    st.plotly_chart(
        px.scatter(home_games.sort_values("Date"), x="Date", y="SellThroughRate", color="Opponent",
                   size="Attendance", title="Sell-Through Rate Over Time", hover_data=["Opponent", "Attendance", "Capacity"]),
        use_container_width=True,
    )

    st.subheader("Game Log")
    st.dataframe(
        home_games[["GameID", "Date", "Opponent", "Competition", "DayOfWeek", "Weather", "Attendance", "Capacity", "SellThroughRate"]]
        .sort_values("Date", ascending=False),
        use_container_width=True, hide_index=True,
    )


def page_customer_analytics(data: dict, fact: pd.DataFrame) -> None:
    st.title("Customer Analytics")

    segmented, summary = load_segments()

    st.subheader("RFM Lifecycle Segments")
    st.dataframe(summary, use_container_width=True, hide_index=True)
    st.plotly_chart(px.bar(summary, x="RFM_Segment", y="Customers", color="AvgLifetimeSpend",
                            title="Customers per RFM Segment"), use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        gender = data["customers"]["Gender"].value_counts().reset_index()
        gender.columns = ["Gender", "Customers"]
        st.plotly_chart(px.pie(gender, names="Gender", values="Customers", title="Customer Gender Mix"),
                         use_container_width=True)
    with c2:
        age_group = data["customers"]["AgeGroup"].value_counts().sort_index().reset_index()
        age_group.columns = ["AgeGroup", "Customers"]
        st.plotly_chart(px.bar(age_group, x="AgeGroup", y="Customers", title="Customers by Age Group"),
                         use_container_width=True)

    st.subheader("Fan Base Geographic Distribution")
    state_counts = data["customers"].groupby("State").size().reset_index(name="Customers")
    fig = px.choropleth(
        state_counts, locations="State", locationmode="USA-states", color="Customers",
        scope="usa", color_continuous_scale="Blues", title="Customers by State",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Top ZIP Codes by Revenue (current filters)")
    if not fact.empty:
        top_zip = fact.groupby(["ZipCode", "State"])["Revenue"].sum().sort_values(ascending=False).head(15).reset_index()
        st.dataframe(top_zip, use_container_width=True, hide_index=True)


def page_campaign_performance(data: dict) -> None:
    st.title("Campaign Performance")
    ticket_sales = data["ticket_sales"]
    campaigns = data["campaigns"]

    attributed = ticket_sales.groupby("CampaignID").agg(
        Tickets=("TicketID", "count"), Revenue=("Revenue", "sum")
    )
    campaign_view = campaigns.set_index("CampaignID").join(attributed).fillna(0)
    campaign_view["ROIPct"] = ((campaign_view["Revenue"] - campaign_view["Cost"]) / campaign_view["Cost"] * 100).round(1)
    campaign_view = campaign_view.reset_index().sort_values("ROIPct", ascending=False)

    st.plotly_chart(
        px.bar(campaign_view, x="CampaignName", y="ROIPct", color="CampaignType", title="Campaign ROI (%)"),
        use_container_width=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        by_type = campaign_view.groupby("CampaignType").agg(Cost=("Cost", "sum"), Revenue=("Revenue", "sum")).reset_index()
        st.plotly_chart(px.bar(by_type, x="CampaignType", y=["Cost", "Revenue"], barmode="group",
                                title="Cost vs Attributed Revenue by Channel"), use_container_width=True)
    with c2:
        st.plotly_chart(px.scatter(campaign_view, x="DiscountPercentage", y="Tickets", size="Revenue",
                                    color="CampaignType", hover_name="CampaignName",
                                    title="Discount Depth vs Ticket Volume"), use_container_width=True)

    st.subheader("Campaign Detail")
    st.dataframe(campaign_view, use_container_width=True, hide_index=True)


def page_forecasting() -> None:
    st.title("Forecasting")
    st.caption("Linear Regression vs Random Forest, trained on home-game features. Small sample (46 home games) — treat as directional, not production-grade.")

    results = load_forecasts()

    for label, key in [("Attendance", "attendance"), ("Revenue", "revenue")]:
        st.subheader(f"{label} Forecast")
        result = results[key]
        metrics_df = pd.DataFrame(result["metrics"]).T.reset_index().rename(columns={"index": "Model"})
        st.dataframe(metrics_df, use_container_width=True, hide_index=True)

        top_features = result["feature_importance"].sort_values("Importance", ascending=False).groupby("Model").head(6)
        st.plotly_chart(
            px.bar(top_features, x="Feature", y="Importance", color="Model", barmode="group",
                   title=f"Top Feature Importance — {label}"),
            use_container_width=True,
        )


def page_sql_explorer() -> None:
    st.title("SQL Explorer")
    st.caption("Read-only query console against database/ticket_sales.db. Only SELECT statements are permitted.")

    with open(Path(__file__).resolve().parent.parent / "sql" / "business_queries.sql") as f:
        query_file = f.read()
    preset_queries = {}
    current_label, current_sql = None, []
    for line in query_file.splitlines():
        if line.strip().startswith("-- Q") and "." in line:
            if current_label:
                preset_queries[current_label] = "\n".join(current_sql).strip()
            current_label = line.strip("- ").strip()
            current_sql = []
        elif current_label is not None:
            current_sql.append(line)
    if current_label:
        preset_queries[current_label] = "\n".join(current_sql).strip()

    choice = st.selectbox("Load a preset query (optional)", ["-- custom --"] + list(preset_queries.keys()))
    default_sql = preset_queries.get(choice, "SELECT * FROM ticket_sales LIMIT 100;")
    sql_text = st.text_area("SQL query", value=default_sql, height=180)

    if st.button("Run query"):
        cleaned = sql_text.strip().rstrip(";")
        if not cleaned.lower().lstrip().startswith(("select", "with")):
            st.error("Only SELECT / WITH (CTE) read queries are permitted in the explorer.")
        else:
            try:
                result = pd.read_sql_query(cleaned, get_engine())
                st.success(f"{len(result):,} rows returned")
                st.dataframe(result, use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error(f"Query failed: {exc}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    data = load_data()
    fact = build_fact_table(data)

    page = st.sidebar.radio(
        "Page",
        ["Executive Overview", "Revenue", "Attendance", "Customer Analytics",
         "Campaign Performance", "Forecasting", "SQL Explorer"],
    )

    filtered_fact = render_filters(fact) if page in (
        "Executive Overview", "Revenue", "Attendance", "Customer Analytics"
    ) else fact

    if page == "Executive Overview":
        page_executive_overview(data, filtered_fact)
    elif page == "Revenue":
        page_revenue(filtered_fact)
    elif page == "Attendance":
        page_attendance(data, filtered_fact)
    elif page == "Customer Analytics":
        page_customer_analytics(data, filtered_fact)
    elif page == "Campaign Performance":
        page_campaign_performance(data)
    elif page == "Forecasting":
        page_forecasting()
    elif page == "SQL Explorer":
        page_sql_explorer()


if __name__ == "__main__":
    main()
