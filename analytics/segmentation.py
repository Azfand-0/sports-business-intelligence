"""RFM (Recency, Frequency, Monetary) customer segmentation.

Classifies every ticket-buying fan into one of six lifecycle segments:
VIP, Loyal, Occasional, New, At Risk, Lost. Each segment gets a business
recommendation for the CRM/marketing team to act on.

Fans who signed up in the CRM but never purchased a ticket are reported
separately as "Never Purchased" since they have no transactional signal
to score.
"""
from __future__ import annotations

import pandas as pd

from analytics.db_utils import read_table
from config.config import resolve_path, load_config
from etl.logging_utils import get_logger

logger = get_logger(__name__)
CFG = load_config()

SEGMENT_RECOMMENDATIONS = {
    "VIP": (
        "Highest recency, frequency, and spend. Protect this relationship with "
        "priority renewal windows, dedicated account management, and early access "
        "to playoff/cup tickets. Churn here is the most expensive to replace."
    ),
    "Loyal": (
        "Frequent, fairly recent buyers who aren't yet top spenders. Upsell to "
        "season packages or premium seating and enroll them in a loyalty points "
        "program to nudge them toward VIP status."
    ),
    "Occasional": (
        "Buy a handful of games a season, usually reactively. Target with "
        "single-game flash sales and themed promotion nights (rival week, "
        "family day) that map to the games they already attend."
    ),
    "New": (
        "First purchase within the last 90 days. Send a structured welcome "
        "series (venue guide, next-game reminder, first-purchase discount) to "
        "convert a trial visit into a second purchase, the highest-leverage "
        "moment in the lifecycle."
    ),
    "At Risk": (
        "Previously frequent buyers who have gone quiet (60-180 days recency, "
        "still moderate frequency). Trigger a win-back campaign with a "
        "personalized discount before they lapse into 'Lost'."
    ),
    "Lost": (
        "No purchase in over a year. Low-cost reactivation only (email/SMS "
        "blast, broad promotions); don't spend premium marketing budget "
        "here until they show renewed engagement."
    ),
    "Never Purchased": (
        "In the CRM (newsletter signup, account creation) but has never bought "
        "a ticket. Nurture with top-of-funnel content and first-ticket "
        "incentives rather than loyalty offers."
    ),
}


def _score_quintile(series: pd.Series, worst_is_high_value: bool) -> pd.Series:
    """Score a series into 1-5 quintiles where 5 is always 'best'.

    For Recency, a *large* raw value is worse (stale), so
    ``worst_is_high_value=True`` ranks descending first so the largest raw
    value lands in rank 1 ("worst"). For Frequency/Monetary, a large raw
    value is better, so ranking ascending puts the smallest value at rank 1.
    Either way, rank 1 is always the worst customer, and qcut then maps
    rank order directly onto ascending labels 1-5.
    """
    ranks = series.rank(method="first", ascending=not worst_is_high_value)
    return pd.qcut(ranks, 5, labels=[1, 2, 3, 4, 5]).astype(int)


def classify_segment(row: pd.Series) -> str:
    """Business rule engine mapping R/F/M scores (1-5) to a lifecycle segment."""
    r, f, m = row["R_Score"], row["F_Score"], row["M_Score"]

    if r >= 4 and f >= 4 and m >= 4:
        return "VIP"
    if r <= 2 and f <= 2:
        return "Lost"
    if r <= 3 and f >= 3:
        return "At Risk"
    if f >= 4 and r >= 3:
        return "Loyal"
    if r >= 4 and f <= 2:
        return "New"
    return "Occasional"


def compute_rfm_segments(customers: pd.DataFrame) -> pd.DataFrame:
    """Score and segment every customer with at least one purchase."""
    buyers = customers[customers["Frequency"] > 0].copy()
    never_purchased = customers[customers["Frequency"] == 0].copy()

    buyers["R_Score"] = _score_quintile(buyers["Recency"], worst_is_high_value=True)     # stale = high Recency = worst
    buyers["F_Score"] = _score_quintile(buyers["Frequency"], worst_is_high_value=False)  # low frequency = worst
    buyers["M_Score"] = _score_quintile(buyers["LifetimeSpend"], worst_is_high_value=False)
    buyers["RFM_Segment"] = buyers.apply(classify_segment, axis=1)

    never_purchased["R_Score"] = 0
    never_purchased["F_Score"] = 0
    never_purchased["M_Score"] = 0
    never_purchased["RFM_Segment"] = "Never Purchased"

    result = pd.concat([buyers, never_purchased], ignore_index=True)
    return result


def segment_summary(segmented: pd.DataFrame) -> pd.DataFrame:
    """Aggregate segment sizes, average spend, and recommendation text."""
    summary = segmented.groupby("RFM_Segment").agg(
        Customers=("CustomerID", "count"),
        AvgRecencyDays=("Recency", "mean"),
        AvgFrequency=("Frequency", "mean"),
        AvgLifetimeSpend=("LifetimeSpend", "mean"),
        TotalLifetimeSpend=("LifetimeSpend", "sum"),
    ).round(2).reset_index()
    summary["Recommendation"] = summary["RFM_Segment"].map(SEGMENT_RECOMMENDATIONS)
    return summary.sort_values("TotalLifetimeSpend", ascending=False)


def run_segmentation(persist: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """End-to-end segmentation run against the warehouse."""
    logger.info("Loading customers from warehouse for RFM segmentation")
    customers = read_table("customers")
    segmented = compute_rfm_segments(customers)
    summary = segment_summary(segmented)

    logger.info("Segment distribution:\n%s", summary[["RFM_Segment", "Customers", "AvgLifetimeSpend"]].to_string(index=False))

    if persist:
        processed_dir = resolve_path(CFG["paths"]["processed_dir"])
        processed_dir.mkdir(parents=True, exist_ok=True)
        segmented.to_csv(processed_dir / "customer_segments.csv", index=False)

        reports_dir = resolve_path(CFG["paths"]["reports_dir"])
        reports_dir.mkdir(parents=True, exist_ok=True)
        summary.to_csv(reports_dir / "rfm_segment_summary.csv", index=False)
        logger.info("Segmentation outputs written to data/processed and reports/")

    return segmented, summary


if __name__ == "__main__":
    _, summary_df = run_segmentation()
    print(summary_df.to_string(index=False))
