# Meridian City FC — Executive Business Intelligence Summary

Period covered: 2023-24 and 2024-25 seasons
Source: `database/ticket_sales.db`, refreshed via the ETL pipeline in `etl/`

Every number below comes from a query you can run yourself against the warehouse (see
`sql/business_queries.sql` and `analytics/kpi_calculations.py`). Nothing here is
hand-picked or asserted without something to back it up.

## Headline numbers

| Metric | Value |
|---|---|
| Total revenue (ticketing + merchandise) | $7,886,979 |
| Ticket revenue | $6,717,126 |
| Merchandise revenue | $1,169,853 |
| Average sell-through rate (home games) | 45.5% |
| Average ticket price | $63.83 |
| Season ticket holder share of customer base | 11.9% |
| Season ticket holder share of ticket revenue | 64.2% |
| Season ticket renewal rate (season 1 to season 2) | 93.0% |
| Repeat purchase rate (bought tickets to 2+ games) | 74.2% |
| Average campaign ROI | 549.5% |

## Key insights

1. **Weekend matches draw 15.2% more fans** than weekday fixtures, home games only.
   Where the league schedule allows any flexibility on cup fixtures, that's worth pushing
   toward weekend slots.

2. **Premium seating carries the business.** Premium Club and Midfield Club together
   pull in 57.0% of ticket revenue from only 38.4% of tickets sold. These are the
   highest-priced sections and where season ticket holders concentrate, so protecting and
   growing that inventory matters more than any single promotion.

3. **Rain knocks attendance down 27.9%** compared to clear weather, and snow does worse
   still. Weather-triggered promotions, an automatic concourse discount on forecasted
   rain nights, say, would be worth testing.

4. **Rivalry is the biggest lever in the whole dataset.** Rival games draw 60.9% more
   fans than everything else. Renewal messaging and single-game inventory releases
   should be timed around that calendar, not spread evenly across the season.

5. **Season ticket holders punch way above their weight.** They're 11.9% of the customer
   file but 64.2% of ticket revenue, with a 93.0% season-over-season retention rate.
   Losing even a couple points of that retention costs more than most single-game
   marketing pushes could ever make back.

6. **Email still wins.** It's the top marketing channel by a wide margin: $238,135 in
   attributed ticket revenue, more than double Direct Mail ($113,991) and about 8x Social
   Media ($29,837). For pure ticket-revenue purposes, budget should keep weighting toward
   CRM and email over paid social, though social probably carries brand value this
   attribution model doesn't capture.

7. **Student pricing does exactly what it's supposed to.** Average price drops 77.2%
   ($14.56 vs. a $63.83 blended average) but it's filling seats in the Student Section
   that would otherwise sit empty, without touching premium-section pricing.

8. **Promotion nights help, modestly.** About a 5.1% attendance lift on average, real but
   small next to structural drivers like rivalry or day of week. Promotions work better
   as a floor under weak fixtures than as a way to drive genuinely strong demand.

9. **Holiday fixtures show a real but easy-to-miss lift.** Once you control for weekday
   and weather, the regression coefficient comes out to roughly +7% (see
   `reports/forecasting_report.md`). The raw average without controls is actually
   negative, which is misleading: only 5 of 46 home games fall in a holiday window in
   this dataset, and several happen to land on bad-weather weeknights that mask the real
   effect. Flagging this explicitly rather than quietly picking whichever number looked
   better.

10. **Repeat purchase rate sits at 74.2%,** so most buyers aren't one-and-done, which
    says the acquisition side is healthy. The bigger opportunity is in the "At Risk" and
    "Lost" segments from the RFM model (`analytics/segmentation.py`), which together
    represent more than $6.6M in historical spend that's gone quiet.

## Segment-level recommendations

Full text lives in `analytics/segmentation.py::SEGMENT_RECOMMENDATIONS`. Short version:

- VIP / Loyal: protect with priority renewal windows and dedicated account management.
- At Risk: the largest pool of historical spend sitting outside the active fanbase, so
  this is the highest-priority win-back target.
- New: converting a first purchase into a second one is the single highest-leverage
  moment in the whole lifecycle.
- Lost / Never Purchased: low-cost reactivation only. Not worth over-investing here.

## Caveats

- This is a synthetic dataset built to mirror realistic sports-business dynamics (see
  `etl/generate_data.py` for the full behavioral model). The dollar figures are
  illustrative, not real Meridian City FC financials.
- The forecasting models in `analytics/forecasting.py` train on 46 home games, which is
  enough to trust the feature importance directionally but not enough for production-grade
  point forecasts. Read the R² numbers with that in mind.
