# Data Quality Report

Generated: 2026-07-01T19:06:55.782860

## Missing Values
- **customers**: {'Age': 546, 'City': 175, 'ZipCode': 180, 'Email': 365, 'PreferredSeatSection': 362}
- **campaigns**: none
- **games**: {'Weather': 1, 'Temperature': 1, 'TicketsSold': 38}
- **ticket_sales**: {'CampaignID': 91462, 'Discount': 2032, 'Fees': 2028, 'PaymentMethod': 1008}
- **merchandise**: none

## Duplicate Rows
- **customers**: 180
- **campaigns**: 0
- **games**: 0
- **ticket_sales**: 1499
- **merchandise**: 0

## Referential Integrity
- **orphan_customer_fk**: 0
- **orphan_game_fk**: 0
- **orphan_campaign_fk**: 0

## Malformed ZIP Codes
- 548

## Negative Prices
- **negative_price_paid**: 499
- **negative_revenue**: 499

## Purchases After Game Date
- 954

## Non-ISO Game Dates
- 3