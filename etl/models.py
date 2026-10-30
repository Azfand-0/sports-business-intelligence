"""SQLAlchemy ORM models for the ticket_sales.db warehouse.

Mirrors ``sql/schema.sql`` exactly. Defining the schema through the ORM
instead of raw DDL means the rest of the codebase, and anything else built
on top of this warehouse later, can reflect and query the tables with
proper type safety.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"

    CustomerID = Column(Integer, primary_key=True)
    FirstName = Column(String, nullable=False)
    LastName = Column(String, nullable=False)
    Age = Column(Integer, nullable=False)
    Gender = Column(String)
    City = Column(String)
    State = Column(String)
    ZipCode = Column(String)
    Email = Column(String)
    SignupDate = Column(String, nullable=False)
    SeasonTicketHolder = Column(Boolean, nullable=False)
    CustomerSegment = Column(String)
    CrmReportedLifetimeSpend = Column(Float)
    LifetimeSpend = Column(Float, nullable=False, default=0)
    PreferredSeatSection = Column(String)
    FavoriteOpponent = Column(String)
    Recency = Column(Integer)
    Frequency = Column(Integer, nullable=False, default=0)
    TenureDays = Column(Integer)
    AgeGroup = Column(String)

    ticket_sales = relationship("TicketSale", back_populates="customer")
    merchandise = relationship("Merchandise", back_populates="customer")

    __table_args__ = (
        CheckConstraint("Age BETWEEN 5 AND 100", name="ck_customer_age"),
        Index("idx_customers_segment", "CustomerSegment"),
        Index("idx_customers_sth", "SeasonTicketHolder"),
        Index("idx_customers_zip", "ZipCode"),
    )


class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"

    CampaignID = Column(Integer, primary_key=True)
    CampaignName = Column(String, nullable=False)
    CampaignType = Column(String, nullable=False)
    StartDate = Column(String, nullable=False)
    EndDate = Column(String, nullable=False)
    Cost = Column(Float, nullable=False)
    TargetAudience = Column(String)
    DiscountPercentage = Column(Float)

    ticket_sales = relationship("TicketSale", back_populates="campaign")

    __table_args__ = (
        CheckConstraint("Cost >= 0", name="ck_campaign_cost"),
        CheckConstraint("DiscountPercentage BETWEEN 0 AND 1", name="ck_campaign_discount"),
    )


class Game(Base):
    __tablename__ = "games"

    GameID = Column(Integer, primary_key=True)
    Season = Column(String, nullable=False)
    Date = Column(String, nullable=False)
    Opponent = Column(String, nullable=False)
    Competition = Column(String, nullable=False)
    DayOfWeek = Column(String)
    KickoffTime = Column(String)
    Weather = Column(String)
    Temperature = Column(Float)
    PromotionNight = Column(Boolean)
    Capacity = Column(Integer, nullable=False)
    HomeAway = Column(String, nullable=False)
    OpponentRanking = Column(Integer)
    WinStreak = Column(Integer)
    TicketsSold = Column(Float)
    Attendance = Column(Integer)
    IsWeekend = Column(Boolean)
    IsHoliday = Column(Boolean)
    Month = Column(Integer)
    Year = Column(Integer)
    SellThroughRate = Column(Float)
    IsRivalGame = Column(Boolean)

    ticket_sales = relationship("TicketSale", back_populates="game")
    merchandise = relationship("Merchandise", back_populates="game")

    __table_args__ = (
        CheckConstraint("Capacity > 0", name="ck_game_capacity"),
        CheckConstraint("HomeAway IN ('Home', 'Away')", name="ck_game_homeaway"),
        Index("idx_games_date", "Date"),
        Index("idx_games_opponent", "Opponent"),
        Index("idx_games_homeaway", "HomeAway"),
    )


class TicketSale(Base):
    __tablename__ = "ticket_sales"

    TicketID = Column(Integer, primary_key=True)
    CustomerID = Column(Integer, ForeignKey("customers.CustomerID"), nullable=False)
    GameID = Column(Integer, ForeignKey("games.GameID"), nullable=False)
    CampaignID = Column(Integer, ForeignKey("marketing_campaigns.CampaignID"))
    PurchaseDate = Column(String, nullable=False)
    GameDate = Column(String, nullable=False)
    PurchaseLeadTimeDays = Column(Integer)
    PurchaseMonth = Column(String)
    PurchaseChannel = Column(String)
    TicketType = Column(String)
    SeatSection = Column(String)
    SeatNumber = Column(String)
    PricePaid = Column(Float, nullable=False)
    Discount = Column(Float, nullable=False, default=0)
    Fees = Column(Float, nullable=False, default=0)
    Revenue = Column(Float, nullable=False)
    PaymentMethod = Column(String)
    Scanned = Column(Boolean)
    Attended = Column(Boolean)

    customer = relationship("Customer", back_populates="ticket_sales")
    game = relationship("Game", back_populates="ticket_sales")
    campaign = relationship("MarketingCampaign", back_populates="ticket_sales")

    __table_args__ = (
        CheckConstraint("PricePaid >= 0", name="ck_ticket_price"),
        CheckConstraint("Revenue >= 0", name="ck_ticket_revenue"),
        Index("idx_ticket_sales_customer", "CustomerID"),
        Index("idx_ticket_sales_game", "GameID"),
        Index("idx_ticket_sales_campaign", "CampaignID"),
        Index("idx_ticket_sales_purchase_date", "PurchaseDate"),
        Index("idx_ticket_sales_section", "SeatSection"),
    )


class Merchandise(Base):
    __tablename__ = "merchandise"

    MerchandiseID = Column(Integer, primary_key=True, autoincrement=True)
    CustomerID = Column(Integer, ForeignKey("customers.CustomerID"), nullable=False)
    GameID = Column(Integer, ForeignKey("games.GameID"), nullable=False)
    Category = Column(String, nullable=False)
    AmountSpent = Column(Float, nullable=False)

    customer = relationship("Customer", back_populates="merchandise")
    game = relationship("Game", back_populates="merchandise")

    __table_args__ = (
        CheckConstraint("AmountSpent >= 0", name="ck_merch_amount"),
        Index("idx_merch_customer", "CustomerID"),
        Index("idx_merch_game", "GameID"),
        Index("idx_merch_category", "Category"),
    )
