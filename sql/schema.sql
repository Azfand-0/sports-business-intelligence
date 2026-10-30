-- ============================================================================
-- Meridian City FC — Sports Business Intelligence Platform
-- Database schema (SQLite dialect)
--
-- This file documents the normalized relational model that backs the
-- ticket_sales.db warehouse. It is applied programmatically by
-- etl/load_database.py via SQLAlchemy, but is kept here as the
-- source-of-truth DDL reference for engineers and reviewers.
-- ============================================================================

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS merchandise;
DROP TABLE IF EXISTS ticket_sales;
DROP TABLE IF EXISTS games;
DROP TABLE IF EXISTS marketing_campaigns;
DROP TABLE IF EXISTS customers;

-- ----------------------------------------------------------------------------
-- CUSTOMERS  (CRM dimension)
-- ----------------------------------------------------------------------------
CREATE TABLE customers (
    CustomerID              INTEGER PRIMARY KEY,
    FirstName               TEXT NOT NULL,
    LastName                TEXT NOT NULL,
    Age                     INTEGER NOT NULL CHECK (Age BETWEEN 5 AND 100),
    Gender                  TEXT,
    City                    TEXT,
    State                   TEXT,
    ZipCode                 TEXT,
    Email                   TEXT,
    SignupDate              TEXT NOT NULL,
    SeasonTicketHolder      INTEGER NOT NULL CHECK (SeasonTicketHolder IN (0, 1)),
    CustomerSegment         TEXT,
    CrmReportedLifetimeSpend REAL,
    LifetimeSpend           REAL NOT NULL DEFAULT 0,
    PreferredSeatSection    TEXT,
    FavoriteOpponent        TEXT,
    Recency                 INTEGER,
    Frequency               INTEGER NOT NULL DEFAULT 0,
    TenureDays              INTEGER,
    AgeGroup                TEXT
);

CREATE INDEX idx_customers_segment ON customers (CustomerSegment);
CREATE INDEX idx_customers_sth ON customers (SeasonTicketHolder);
CREATE INDEX idx_customers_zip ON customers (ZipCode);

-- ----------------------------------------------------------------------------
-- MARKETING_CAMPAIGNS  (dimension)
-- ----------------------------------------------------------------------------
CREATE TABLE marketing_campaigns (
    CampaignID          INTEGER PRIMARY KEY,
    CampaignName        TEXT NOT NULL,
    CampaignType        TEXT NOT NULL,
    StartDate           TEXT NOT NULL,
    EndDate             TEXT NOT NULL,
    Cost                REAL NOT NULL CHECK (Cost >= 0),
    TargetAudience      TEXT,
    DiscountPercentage  REAL CHECK (DiscountPercentage BETWEEN 0 AND 1)
);

-- ----------------------------------------------------------------------------
-- GAMES  (fixture / operations dimension)
-- ----------------------------------------------------------------------------
CREATE TABLE games (
    GameID           INTEGER PRIMARY KEY,
    Season           TEXT NOT NULL,
    Date             TEXT NOT NULL,
    Opponent         TEXT NOT NULL,
    Competition      TEXT NOT NULL,
    DayOfWeek        TEXT,
    KickoffTime      TEXT,
    Weather          TEXT,
    Temperature      REAL,
    PromotionNight   INTEGER CHECK (PromotionNight IN (0, 1)),
    Capacity         INTEGER NOT NULL CHECK (Capacity > 0),
    HomeAway         TEXT NOT NULL CHECK (HomeAway IN ('Home', 'Away')),
    OpponentRanking  INTEGER,
    WinStreak        INTEGER,
    TicketsSold      REAL,
    Attendance       INTEGER CHECK (Attendance >= 0),
    IsWeekend        INTEGER CHECK (IsWeekend IN (0, 1)),
    IsHoliday        INTEGER CHECK (IsHoliday IN (0, 1)),
    Month            INTEGER,
    Year             INTEGER,
    SellThroughRate  REAL,
    IsRivalGame      INTEGER CHECK (IsRivalGame IN (0, 1))
);

CREATE INDEX idx_games_date ON games (Date);
CREATE INDEX idx_games_opponent ON games (Opponent);
CREATE INDEX idx_games_homeaway ON games (HomeAway);

-- ----------------------------------------------------------------------------
-- TICKET_SALES  (fact table)
-- ----------------------------------------------------------------------------
CREATE TABLE ticket_sales (
    TicketID              INTEGER PRIMARY KEY,
    CustomerID            INTEGER NOT NULL REFERENCES customers (CustomerID),
    GameID                INTEGER NOT NULL REFERENCES games (GameID),
    CampaignID            INTEGER REFERENCES marketing_campaigns (CampaignID),
    PurchaseDate          TEXT NOT NULL,
    GameDate              TEXT NOT NULL,
    PurchaseLeadTimeDays  INTEGER,
    PurchaseMonth         TEXT,
    PurchaseChannel       TEXT,
    TicketType            TEXT,
    SeatSection           TEXT,
    SeatNumber            TEXT,
    PricePaid             REAL NOT NULL CHECK (PricePaid >= 0),
    Discount              REAL NOT NULL DEFAULT 0,
    Fees                  REAL NOT NULL DEFAULT 0,
    Revenue               REAL NOT NULL CHECK (Revenue >= 0),
    PaymentMethod         TEXT,
    Scanned               INTEGER CHECK (Scanned IN (0, 1)),
    Attended              INTEGER CHECK (Attended IN (0, 1))
);

CREATE INDEX idx_ticket_sales_customer ON ticket_sales (CustomerID);
CREATE INDEX idx_ticket_sales_game ON ticket_sales (GameID);
CREATE INDEX idx_ticket_sales_campaign ON ticket_sales (CampaignID);
CREATE INDEX idx_ticket_sales_purchase_date ON ticket_sales (PurchaseDate);
CREATE INDEX idx_ticket_sales_section ON ticket_sales (SeatSection);

-- ----------------------------------------------------------------------------
-- MERCHANDISE  (fact table)
-- ----------------------------------------------------------------------------
CREATE TABLE merchandise (
    MerchandiseID   INTEGER PRIMARY KEY AUTOINCREMENT,
    CustomerID      INTEGER NOT NULL REFERENCES customers (CustomerID),
    GameID          INTEGER NOT NULL REFERENCES games (GameID),
    Category        TEXT NOT NULL,
    AmountSpent     REAL NOT NULL CHECK (AmountSpent >= 0)
);

CREATE INDEX idx_merch_customer ON merchandise (CustomerID);
CREATE INDEX idx_merch_game ON merchandise (GameID);
CREATE INDEX idx_merch_category ON merchandise (Category);
