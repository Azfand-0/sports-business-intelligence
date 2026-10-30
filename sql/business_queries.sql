-- ============================================================================
-- Meridian City FC — Business Intelligence Query Library
-- Target: SQLite (database/ticket_sales.db)
--
-- 38 production-style analytical queries organized by business domain.
-- Techniques demonstrated are called out inline: INNER/LEFT JOIN, GROUP BY,
-- CASE, CTEs, and window functions (ROW_NUMBER, RANK, LAG, running totals).
-- ============================================================================


-- ----------------------------------------------------------------------------
-- SECTION 1: REVENUE
-- ----------------------------------------------------------------------------

-- Q1. Top 20 customers by total revenue [INNER JOIN, GROUP BY, ORDER BY]
SELECT
    c.CustomerID,
    c.FirstName || ' ' || c.LastName AS CustomerName,
    c.CustomerSegment,
    COUNT(t.TicketID) AS TotalTickets,
    ROUND(SUM(t.Revenue), 2) AS TotalRevenue
FROM customers c
INNER JOIN ticket_sales t ON t.CustomerID = c.CustomerID
GROUP BY c.CustomerID, c.FirstName, c.LastName, c.CustomerSegment
ORDER BY TotalRevenue DESC
LIMIT 20;

-- Q2. Revenue by month across both seasons [GROUP BY, strftime]
SELECT
    strftime('%Y-%m', PurchaseDate) AS PurchaseMonth,
    COUNT(*) AS TicketsSold,
    ROUND(SUM(Revenue), 2) AS MonthlyRevenue
FROM ticket_sales
GROUP BY PurchaseMonth
ORDER BY PurchaseMonth;

-- Q3. Monthly revenue growth % month-over-month [CTE, LAG window function]
WITH monthly AS (
    SELECT strftime('%Y-%m', PurchaseDate) AS PurchaseMonth,
           SUM(Revenue) AS Revenue
    FROM ticket_sales
    GROUP BY PurchaseMonth
)
SELECT
    PurchaseMonth,
    ROUND(Revenue, 2) AS Revenue,
    ROUND(LAG(Revenue) OVER (ORDER BY PurchaseMonth), 2) AS PriorMonthRevenue,
    ROUND(
        100.0 * (Revenue - LAG(Revenue) OVER (ORDER BY PurchaseMonth))
        / NULLIF(LAG(Revenue) OVER (ORDER BY PurchaseMonth), 0), 2
    ) AS MoMGrowthPct
FROM monthly
ORDER BY PurchaseMonth;

-- Q4. Revenue pacing: running (cumulative) total revenue per season [Window running total]
SELECT
    g.Season,
    t.PurchaseDate,
    ROUND(SUM(t.Revenue), 2) AS DailyRevenue,
    ROUND(SUM(SUM(t.Revenue)) OVER (
        PARTITION BY g.Season ORDER BY t.PurchaseDate
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ), 2) AS CumulativeSeasonRevenue
FROM ticket_sales t
INNER JOIN games g ON g.GameID = t.GameID
GROUP BY g.Season, t.PurchaseDate
ORDER BY g.Season, t.PurchaseDate;

-- Q5. Revenue by seat section with share of total [Window SUM() OVER () for grand total]
SELECT
    SeatSection,
    COUNT(*) AS TicketsSold,
    ROUND(SUM(Revenue), 2) AS SectionRevenue,
    ROUND(100.0 * SUM(Revenue) / SUM(SUM(Revenue)) OVER (), 2) AS PctOfTotalRevenue
FROM ticket_sales
GROUP BY SeatSection
ORDER BY SectionRevenue DESC;

-- Q6. Revenue by ticket type [GROUP BY]
SELECT
    TicketType,
    COUNT(*) AS TicketCount,
    ROUND(AVG(PricePaid), 2) AS AvgPricePaid,
    ROUND(SUM(Revenue), 2) AS TotalRevenue
FROM ticket_sales
GROUP BY TicketType
ORDER BY TotalRevenue DESC;

-- Q7. Revenue by payment method [GROUP BY]
SELECT
    PaymentMethod,
    COUNT(*) AS Transactions,
    ROUND(SUM(Revenue), 2) AS TotalRevenue,
    ROUND(AVG(Revenue), 2) AS AvgTransactionValue
FROM ticket_sales
GROUP BY PaymentMethod
ORDER BY TotalRevenue DESC;

-- Q8. Average ticket price by seat section and ticket type [GROUP BY, CASE]
SELECT
    SeatSection,
    ROUND(AVG(PricePaid), 2) AS AvgPrice,
    ROUND(AVG(CASE WHEN TicketType = 'Season' THEN PricePaid END), 2) AS AvgSeasonPrice,
    ROUND(AVG(CASE WHEN TicketType = 'Individual Game' THEN PricePaid END), 2) AS AvgIndividualPrice
FROM ticket_sales
GROUP BY SeatSection
ORDER BY AvgPrice DESC;

-- Q9. Most profitable opponent [INNER JOIN, GROUP BY]
SELECT
    g.Opponent,
    COUNT(t.TicketID) AS TicketsSold,
    ROUND(SUM(t.Revenue), 2) AS TotalRevenue,
    ROUND(AVG(g.SellThroughRate), 3) AS AvgSellThroughRate
FROM games g
INNER JOIN ticket_sales t ON t.GameID = g.GameID
WHERE g.HomeAway = 'Home'
GROUP BY g.Opponent
ORDER BY TotalRevenue DESC;

-- Q10. Premium seating share of revenue vs share of seats sold [CASE, aggregation]
SELECT
    CASE WHEN SeatSection IN ('Premium Club', 'Midfield Club') THEN 'Premium' ELSE 'Standard' END AS SeatTier,
    COUNT(*) AS TicketsSold,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM ticket_sales), 2) AS PctOfTicketsSold,
    ROUND(SUM(Revenue), 2) AS Revenue,
    ROUND(100.0 * SUM(Revenue) / (SELECT SUM(Revenue) FROM ticket_sales), 2) AS PctOfRevenue
FROM ticket_sales
GROUP BY SeatTier;

-- Q11. Average revenue per fan per game [INNER JOIN, GROUP BY]
SELECT
    g.GameID,
    g.Date,
    g.Opponent,
    COUNT(DISTINCT t.CustomerID) AS UniqueFans,
    ROUND(SUM(t.Revenue), 2) AS GameRevenue,
    ROUND(SUM(t.Revenue) / COUNT(DISTINCT t.CustomerID), 2) AS RevenuePerFan
FROM games g
INNER JOIN ticket_sales t ON t.GameID = g.GameID
GROUP BY g.GameID, g.Date, g.Opponent
ORDER BY GameRevenue DESC
LIMIT 15;

-- Q12. Corporate/Group segment contribution to revenue [INNER JOIN, CASE]
SELECT
    CASE WHEN c.CustomerSegment = 'Corporate/Group' THEN 'Corporate/Group' ELSE 'Individual Fans' END AS BuyerType,
    COUNT(t.TicketID) AS Tickets,
    ROUND(SUM(t.Revenue), 2) AS Revenue
FROM ticket_sales t
INNER JOIN customers c ON c.CustomerID = t.CustomerID
GROUP BY BuyerType;


-- ----------------------------------------------------------------------------
-- SECTION 2: ATTENDANCE
-- ----------------------------------------------------------------------------

-- Q13. Attendance trend by month [GROUP BY]
SELECT
    strftime('%Y-%m', Date) AS GameMonth,
    COUNT(*) AS HomeGames,
    ROUND(AVG(Attendance), 0) AS AvgAttendance,
    ROUND(AVG(SellThroughRate), 3) AS AvgSellThroughRate
FROM games
WHERE HomeAway = 'Home'
GROUP BY GameMonth
ORDER BY GameMonth;

-- Q14. Attendance by day of week [CASE for weekday ordering, GROUP BY]
SELECT
    DayOfWeek,
    COUNT(*) AS Games,
    ROUND(AVG(Attendance), 0) AS AvgAttendance,
    ROUND(AVG(SellThroughRate), 3) AS AvgSellThroughRate
FROM games
WHERE HomeAway = 'Home'
GROUP BY DayOfWeek
ORDER BY
    CASE DayOfWeek
        WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3
        WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6 ELSE 7
    END;

-- Q15. Weekend vs weekday attendance lift [CASE]
SELECT
    CASE WHEN IsWeekend = 1 THEN 'Weekend' ELSE 'Weekday' END AS GameTiming,
    COUNT(*) AS Games,
    ROUND(AVG(Attendance), 0) AS AvgAttendance,
    ROUND(AVG(SellThroughRate), 3) AS AvgSellThroughRate
FROM games
WHERE HomeAway = 'Home'
GROUP BY GameTiming;

-- Q16. Weather impact on attendance [GROUP BY, CASE]
SELECT
    Weather,
    COUNT(*) AS Games,
    ROUND(AVG(Attendance), 0) AS AvgAttendance,
    ROUND(AVG(SellThroughRate), 3) AS AvgSellThroughRate
FROM games
WHERE HomeAway = 'Home'
GROUP BY Weather
ORDER BY AvgSellThroughRate DESC;

-- Q17. Promotion night effectiveness [CASE, GROUP BY]
SELECT
    CASE WHEN PromotionNight = 1 THEN 'Promotion Night' ELSE 'Standard Night' END AS NightType,
    COUNT(*) AS Games,
    ROUND(AVG(Attendance), 0) AS AvgAttendance,
    ROUND(AVG(SellThroughRate), 3) AS AvgSellThroughRate
FROM games
WHERE HomeAway = 'Home'
GROUP BY NightType;

-- Q18. Rival games vs non-rival attendance [CASE]
SELECT
    CASE WHEN IsRivalGame = 1 THEN 'Rival' ELSE 'Non-Rival' END AS GameType,
    COUNT(*) AS Games,
    ROUND(AVG(Attendance), 0) AS AvgAttendance,
    ROUND(AVG(SellThroughRate), 3) AS AvgSellThroughRate
FROM games
WHERE HomeAway = 'Home'
GROUP BY GameType;

-- Q19. Holiday match demand lift [CASE]
SELECT
    CASE WHEN IsHoliday = 1 THEN 'Holiday Window' ELSE 'Regular Date' END AS DateType,
    COUNT(*) AS Games,
    ROUND(AVG(Attendance), 0) AS AvgAttendance,
    ROUND(AVG(SellThroughRate), 3) AS AvgSellThroughRate
FROM games
WHERE HomeAway = 'Home'
GROUP BY DateType;

-- Q20. Top 10 highest-attendance games, ranked [Window RANK()]
SELECT
    GameID, Date, Opponent, Attendance, Capacity,
    RANK() OVER (ORDER BY Attendance DESC) AS AttendanceRank
FROM games
WHERE HomeAway = 'Home'
ORDER BY AttendanceRank
LIMIT 10;

-- Q21. Sell-through rate distribution by opponent [GROUP BY]
SELECT
    Opponent,
    COUNT(*) AS Games,
    ROUND(AVG(SellThroughRate), 3) AS AvgSellThroughRate,
    ROUND(MAX(SellThroughRate), 3) AS BestSellThroughRate
FROM games
WHERE HomeAway = 'Home'
GROUP BY Opponent
ORDER BY AvgSellThroughRate DESC;

-- Q22. No-show rate by weather condition [LEFT JOIN, CASE, GROUP BY]
SELECT
    g.Weather,
    COUNT(t.TicketID) AS TicketsSold,
    SUM(CASE WHEN t.Attended = 0 THEN 1 ELSE 0 END) AS NoShows,
    ROUND(100.0 * SUM(CASE WHEN t.Attended = 0 THEN 1 ELSE 0 END) / COUNT(t.TicketID), 2) AS NoShowRatePct
FROM ticket_sales t
LEFT JOIN games g ON g.GameID = t.GameID
GROUP BY g.Weather
ORDER BY NoShowRatePct DESC;

-- Q23. Running total of tickets sold across the season (cumulative demand curve) [Window]
SELECT
    g.Season,
    g.Date,
    g.Attendance,
    SUM(g.Attendance) OVER (PARTITION BY g.Season ORDER BY g.Date) AS CumulativeSeasonAttendance
FROM games g
WHERE g.HomeAway = 'Home'
ORDER BY g.Season, g.Date;


-- ----------------------------------------------------------------------------
-- SECTION 3: CUSTOMER BEHAVIOR & RETENTION
-- ----------------------------------------------------------------------------

-- Q24. Repeat purchase rate: share of customers who bought tickets to more than one game [CTE]
WITH games_per_customer AS (
    SELECT CustomerID, COUNT(DISTINCT GameID) AS DistinctGames
    FROM ticket_sales
    GROUP BY CustomerID
)
SELECT
    COUNT(*) AS TotalBuyers,
    SUM(CASE WHEN DistinctGames > 1 THEN 1 ELSE 0 END) AS RepeatBuyers,
    ROUND(100.0 * SUM(CASE WHEN DistinctGames > 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS RepeatPurchaseRatePct
FROM games_per_customer;

-- Q25. Customer lifetime value ranking within each segment [Window RANK() PARTITION BY]
SELECT
    CustomerID, FirstName, LastName, CustomerSegment, LifetimeSpend,
    RANK() OVER (PARTITION BY CustomerSegment ORDER BY LifetimeSpend DESC) AS SegmentSpendRank
FROM customers
WHERE LifetimeSpend > 0
ORDER BY CustomerSegment, SegmentSpendRank
LIMIT 50;

-- Q26. Top ZIP codes by total revenue [INNER JOIN, GROUP BY]
SELECT
    c.ZipCode,
    c.City,
    c.State,
    COUNT(DISTINCT c.CustomerID) AS Customers,
    ROUND(SUM(t.Revenue), 2) AS TotalRevenue
FROM customers c
INNER JOIN ticket_sales t ON t.CustomerID = c.CustomerID
WHERE c.ZipCode IS NOT NULL
GROUP BY c.ZipCode, c.City, c.State
ORDER BY TotalRevenue DESC
LIMIT 10;

-- Q27. First-time buyers by month [Window ROW_NUMBER()]
WITH ranked_purchases AS (
    SELECT
        CustomerID,
        PurchaseDate,
        ROW_NUMBER() OVER (PARTITION BY CustomerID ORDER BY PurchaseDate) AS PurchaseSeq
    FROM ticket_sales
)
SELECT
    strftime('%Y-%m', PurchaseDate) AS Month,
    COUNT(*) AS FirstTimeBuyers
FROM ranked_purchases
WHERE PurchaseSeq = 1
GROUP BY Month
ORDER BY Month;

-- Q28. Season ticket renewal rate: STH active in season 1 who also bought in season 2 [CTE, LEFT JOIN]
WITH season1_sth AS (
    SELECT DISTINCT t.CustomerID
    FROM ticket_sales t
    INNER JOIN games g ON g.GameID = t.GameID
    WHERE g.Season = '2023-24' AND t.TicketType = 'Season'
),
season2_buyers AS (
    SELECT DISTINCT t.CustomerID
    FROM ticket_sales t
    INNER JOIN games g ON g.GameID = t.GameID
    WHERE g.Season = '2024-25' AND t.TicketType = 'Season'
)
SELECT
    COUNT(*) AS Season1SeasonTicketHolders,
    SUM(CASE WHEN s2.CustomerID IS NOT NULL THEN 1 ELSE 0 END) AS RenewedInSeason2,
    ROUND(100.0 * SUM(CASE WHEN s2.CustomerID IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS RenewalRatePct
FROM season1_sth s1
LEFT JOIN season2_buyers s2 ON s2.CustomerID = s1.CustomerID;

-- Q29. Churn candidates: customers inactive for 180+ days as of their last purchase [CTE]
WITH last_purchase AS (
    SELECT CustomerID, MAX(PurchaseDate) AS LastPurchaseDate
    FROM ticket_sales
    GROUP BY CustomerID
)
SELECT
    c.CustomerID, c.FirstName, c.LastName, c.CustomerSegment,
    lp.LastPurchaseDate,
    CAST(julianday((SELECT MAX(PurchaseDate) FROM ticket_sales)) - julianday(lp.LastPurchaseDate) AS INTEGER) AS DaysInactive
FROM customers c
INNER JOIN last_purchase lp ON lp.CustomerID = c.CustomerID
WHERE julianday((SELECT MAX(PurchaseDate) FROM ticket_sales)) - julianday(lp.LastPurchaseDate) >= 180
ORDER BY DaysInactive DESC
LIMIT 25;

-- Q30. Largest season-over-season spending increase [CTE, LEFT JOIN, self-comparison]
WITH season1_spend AS (
    SELECT t.CustomerID, SUM(t.Revenue) AS Season1Revenue
    FROM ticket_sales t INNER JOIN games g ON g.GameID = t.GameID
    WHERE g.Season = '2023-24'
    GROUP BY t.CustomerID
),
season2_spend AS (
    SELECT t.CustomerID, SUM(t.Revenue) AS Season2Revenue
    FROM ticket_sales t INNER JOIN games g ON g.GameID = t.GameID
    WHERE g.Season = '2024-25'
    GROUP BY t.CustomerID
)
SELECT
    c.CustomerID, c.FirstName, c.LastName,
    ROUND(COALESCE(s1.Season1Revenue, 0), 2) AS Season1Revenue,
    ROUND(COALESCE(s2.Season2Revenue, 0), 2) AS Season2Revenue,
    ROUND(COALESCE(s2.Season2Revenue, 0) - COALESCE(s1.Season1Revenue, 0), 2) AS SpendIncrease
FROM customers c
LEFT JOIN season1_spend s1 ON s1.CustomerID = c.CustomerID
LEFT JOIN season2_spend s2 ON s2.CustomerID = c.CustomerID
ORDER BY SpendIncrease DESC
LIMIT 15;

-- Q31. Purchase channel preference by age group [INNER JOIN, GROUP BY]
SELECT
    c.AgeGroup,
    t.PurchaseChannel,
    COUNT(*) AS Tickets
FROM ticket_sales t
INNER JOIN customers c ON c.CustomerID = t.CustomerID
GROUP BY c.AgeGroup, t.PurchaseChannel
ORDER BY c.AgeGroup, Tickets DESC;

-- Q32. Average purchase lead time (days before game) by ticket type [GROUP BY]
SELECT
    TicketType,
    ROUND(AVG(PurchaseLeadTimeDays), 1) AS AvgLeadTimeDays,
    COUNT(*) AS Tickets
FROM ticket_sales
GROUP BY TicketType
ORDER BY AvgLeadTimeDays DESC;

-- Q33. Top 3 spenders per season [Window ROW_NUMBER() PARTITION BY]
WITH season_spend AS (
    SELECT
        g.Season, t.CustomerID, SUM(t.Revenue) AS SeasonRevenue,
        ROW_NUMBER() OVER (PARTITION BY g.Season ORDER BY SUM(t.Revenue) DESC) AS SpendRank
    FROM ticket_sales t
    INNER JOIN games g ON g.GameID = t.GameID
    GROUP BY g.Season, t.CustomerID
)
SELECT ss.Season, ss.CustomerID, c.FirstName, c.LastName, ROUND(ss.SeasonRevenue, 2) AS SeasonRevenue
FROM season_spend ss
INNER JOIN customers c ON c.CustomerID = ss.CustomerID
WHERE ss.SpendRank <= 3
ORDER BY ss.Season, ss.SpendRank;

-- Q34. Customer signup cohort lifetime value [GROUP BY, CTE]
WITH cohorts AS (
    SELECT CustomerID, strftime('%Y', SignupDate) AS SignupYear
    FROM customers
)
SELECT
    co.SignupYear,
    COUNT(DISTINCT co.CustomerID) AS Customers,
    ROUND(AVG(c.LifetimeSpend), 2) AS AvgLifetimeSpend,
    ROUND(SUM(c.LifetimeSpend), 2) AS CohortTotalSpend
FROM cohorts co
INNER JOIN customers c ON c.CustomerID = co.CustomerID
GROUP BY co.SignupYear
ORDER BY co.SignupYear;

-- Q35. Simple RFM tiering directly in SQL [CASE, CTE — mirrors analytics/segmentation.py]
WITH rfm AS (
    SELECT CustomerID, Recency, Frequency, LifetimeSpend AS Monetary
    FROM customers
    WHERE Frequency > 0
)
SELECT
    CASE
        WHEN Recency <= 60 AND Frequency >= 15 AND Monetary >= 1000 THEN 'VIP'
        WHEN Recency <= 120 AND Frequency >= 6 THEN 'Loyal'
        WHEN Recency <= 200 THEN 'Occasional'
        WHEN Recency > 200 AND Recency <= 365 THEN 'At Risk'
        WHEN Recency > 365 THEN 'Lost'
        ELSE 'New'
    END AS RfmSegment,
    COUNT(*) AS Customers,
    ROUND(AVG(Monetary), 2) AS AvgSpend
FROM rfm
GROUP BY RfmSegment
ORDER BY AvgSpend DESC;


-- ----------------------------------------------------------------------------
-- SECTION 4: MARKETING CAMPAIGN PERFORMANCE
-- ----------------------------------------------------------------------------

-- Q36. Campaign ROI: revenue attributed vs cost [LEFT JOIN, GROUP BY]
SELECT
    mc.CampaignName,
    mc.CampaignType,
    mc.Cost,
    COUNT(t.TicketID) AS AttributedTickets,
    ROUND(SUM(t.Revenue), 2) AS AttributedRevenue,
    ROUND((SUM(t.Revenue) - mc.Cost) / mc.Cost * 100, 1) AS ROIPct
FROM marketing_campaigns mc
LEFT JOIN ticket_sales t ON t.CampaignID = mc.CampaignID
GROUP BY mc.CampaignID, mc.CampaignName, mc.CampaignType, mc.Cost
ORDER BY ROIPct DESC;

-- Q37. Campaign performance by channel type [CTE pre-aggregation avoids join fan-out, LEFT JOIN]
WITH cost_by_type AS (
    SELECT CampaignType, COUNT(*) AS Campaigns, SUM(Cost) AS TotalCost
    FROM marketing_campaigns
    GROUP BY CampaignType
),
revenue_by_type AS (
    SELECT mc.CampaignType, COUNT(t.TicketID) AS AttributedTickets, SUM(t.Revenue) AS AttributedRevenue
    FROM marketing_campaigns mc
    LEFT JOIN ticket_sales t ON t.CampaignID = mc.CampaignID
    GROUP BY mc.CampaignType
)
SELECT
    ct.CampaignType,
    ct.Campaigns,
    ct.TotalCost,
    rt.AttributedTickets,
    ROUND(rt.AttributedRevenue, 2) AS AttributedRevenue
FROM cost_by_type ct
INNER JOIN revenue_by_type rt ON rt.CampaignType = ct.CampaignType
ORDER BY AttributedRevenue DESC;

-- Q38. Discount depth vs resulting ticket volume by campaign [INNER JOIN, GROUP BY]
SELECT
    mc.CampaignName,
    mc.DiscountPercentage,
    COUNT(t.TicketID) AS TicketsSold,
    ROUND(AVG(t.PricePaid), 2) AS AvgPricePaid
FROM marketing_campaigns mc
INNER JOIN ticket_sales t ON t.CampaignID = mc.CampaignID
GROUP BY mc.CampaignID, mc.CampaignName, mc.DiscountPercentage
ORDER BY mc.DiscountPercentage DESC;

-- Q39. Merchandise attach rate and average spend per attending fan [LEFT JOIN, CTE]
WITH attendees AS (
    SELECT CustomerID, GameID FROM ticket_sales WHERE Attended = 1
)
SELECT
    COUNT(DISTINCT a.CustomerID || '-' || a.GameID) AS AttendedTicketVisits,
    COUNT(DISTINCT m.CustomerID || '-' || m.GameID) AS VisitsWithMerchSpend,
    ROUND(100.0 * COUNT(DISTINCT m.CustomerID || '-' || m.GameID) / COUNT(DISTINCT a.CustomerID || '-' || a.GameID), 2) AS AttachRatePct,
    ROUND(AVG(m.AmountSpent), 2) AS AvgMerchSpendPerTransaction
FROM attendees a
LEFT JOIN merchandise m ON m.CustomerID = a.CustomerID AND m.GameID = a.GameID;
