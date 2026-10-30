"""Synthetic data generator for the Meridian City FC Sports BI Platform.

Produces five raw CSV extracts that mimic what would land in a club's
data lake from separate systems of record:

    customers.csv        - CRM
    marketing_campaigns.csv - marketing automation platform
    games.csv             - operations / scheduling system
    ticket_sales.csv      - box office / ticketing platform
    merchandise.csv       - point-of-sale system

The generation logic encodes deliberate behavioral realism (season-ticket
holders attend almost every game, rivalries sell out, rain suppresses
attendance, premium seats drive disproportionate revenue, etc.) and then
deliberately re-introduces the data quality problems (duplicates, nulls,
inconsistent casing, malformed ZIPs, bad dates, negative prices) that a
real BI analyst would have to clean up downstream in ``etl/validate.py``
and ``etl/clean.py``.

Run as a script:  python -m etl.generate_data
"""
from __future__ import annotations

import string
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from faker import Faker

from config.config import load_config, resolve_path
from etl.logging_utils import get_logger

logger = get_logger(__name__)
faker = Faker()

CFG = load_config()
RNG_SEED = CFG["data_generation"]["random_seed"]
rng = np.random.default_rng(RNG_SEED)
Faker.seed(RNG_SEED)

SEAT_SECTIONS = CFG["seat_sections"]
SECTION_NAMES = [s["name"] for s in SEAT_SECTIONS]
SECTION_BASE_PRICE = {s["name"]: s["base_price"] for s in SEAT_SECTIONS}
SECTION_CAPACITY_SHARE = np.array([s["pct_of_capacity"] for s in SEAT_SECTIONS])
SECTION_CAPACITY_SHARE = SECTION_CAPACITY_SHARE / SECTION_CAPACITY_SHARE.sum()
SECTION_CAPACITY_ABS = {
    name: int(round(CFG["club"]["stadium_capacity"] * share))
    for name, share in zip(SECTION_NAMES, SECTION_CAPACITY_SHARE)
}

OPPONENTS = CFG["schedule"]["opponents"]
RIVALS = set(CFG["schedule"]["rival_opponents"])
STADIUM_CAPACITY = CFG["club"]["stadium_capacity"]
SEASONS = CFG["seasons"]

CUSTOMER_SEGMENTS_BY_STH = {
    True: ["Season Ticket Holder", "VIP"],
    False: ["Frequent Attendee", "Occasional Fan", "Single-Game Buyer", "New Fan", "Corporate/Group"],
}

WEATHER_OPTIONS = ["Clear", "Cloudy", "Rain", "Snow", "Windy"]
PAYMENT_METHODS = ["Credit Card", "Debit Card", "Apple Pay", "PayPal", "Cash", "Season Payment Plan"]
PURCHASE_CHANNELS = ["Website", "Mobile App", "Box Office", "Phone", "Season Ticket Portal", "Third-Party Resale"]
MERCH_CATEGORIES = {
    "Jersey": 85.0,
    "Scarf": 25.0,
    "Food & Beverage": 18.0,
    "Program": 10.0,
    "Cap": 22.0,
    "Other": 15.0,
}

HOLIDAY_WINDOWS = [
    # (month, day, day, label) inclusive ranges that fall inside an Aug-May season
    (11, 22, 29),   # Thanksgiving week
    (12, 20, 31),   # Christmas / New Year's Eve
    (1, 1, 2),      # New Year's Day
    (1, 15, 21),    # MLK weekend window
    (2, 14, 17),    # Presidents Day / Valentine's window
]


def _is_holiday(d: date) -> bool:
    """Return True if a date falls inside a heuristic holiday-demand window."""
    for month, start_day, end_day in HOLIDAY_WINDOWS:
        if d.month == month and start_day <= d.day <= end_day:
            return True
    return False


# --------------------------------------------------------------------------- #
# Customers
# --------------------------------------------------------------------------- #
def generate_customers(n_customers: int) -> pd.DataFrame:
    """Generate the CRM customer master file."""
    logger.info("Generating %s customer records", n_customers)
    customer_ids = np.arange(1, n_customers + 1)

    is_sth = rng.random(n_customers) < CFG["data_generation"]["season_ticket_holder_pct"]

    genders = rng.choice(["M", "F", "Other"], size=n_customers, p=[0.55, 0.43, 0.02])
    ages = np.clip(rng.normal(38, 14, size=n_customers), 12, 85).astype(int)

    # 70% local metro fans, 30% out-of-town
    is_local = rng.random(n_customers) < 0.70
    club_city, club_state = CFG["club"]["city"], CFG["club"]["state"]

    first_names, last_names, emails, cities, states, zips = [], [], [], [], [], []
    for local in is_local:
        first = faker.first_name()
        last = faker.last_name()
        first_names.append(first)
        last_names.append(last)
        emails.append(f"{first.lower()}.{last.lower()}{rng.integers(1, 999)}@{faker.free_email_domain()}")
        if local:
            cities.append(club_city)
            states.append(club_state)
            zips.append(f"{rng.integers(44000, 44999)}")
        else:
            cities.append(faker.city())
            states.append(faker.state_abbr())
            zips.append(faker.zipcode())

    # Signup dates: exponentially biased toward more recent years since founding
    founded = date(CFG["club"]["founded"], 1, 1)
    today = datetime.strptime(SEASONS[-1]["end_date"], "%Y-%m-%d").date()
    span_days = (today - founded).days
    skew = rng.beta(2.5, 1.2, size=n_customers)  # skew toward 1 (recent)
    signup_dates = [founded + timedelta(days=int(skew[i] * span_days)) for i in range(n_customers)]
    # Season ticket holders tend to be longer-tenured fans
    for i in np.where(is_sth)[0]:
        signup_dates[i] = founded + timedelta(days=int(rng.beta(1.0, 2.0) * span_days))

    segments = np.array([
        rng.choice(CUSTOMER_SEGMENTS_BY_STH[True]) if sth else rng.choice(
            CUSTOMER_SEGMENTS_BY_STH[False], p=[0.30, 0.35, 0.20, 0.10, 0.05]
        )
        for sth in is_sth
    ])

    preferred_section = np.empty(n_customers, dtype=object)
    for i, seg in enumerate(segments):
        if seg in ("VIP", "Season Ticket Holder"):
            preferred_section[i] = rng.choice(["Premium Club", "Midfield Club"], p=[0.4, 0.6])
        elif ages[i] < 24:
            preferred_section[i] = rng.choice(["Student Section", "Supporters Section"], p=[0.6, 0.4])
        elif seg == "Corporate/Group":
            preferred_section[i] = rng.choice(["Midfield Club", "Lower Bowl"], p=[0.5, 0.5])
        else:
            preferred_section[i] = rng.choice(SECTION_NAMES, p=SECTION_CAPACITY_SHARE)

    favorite_opponent = rng.choice(
        OPPONENTS, size=n_customers,
        p=_weighted_opponent_probs(),
    )

    # Placeholder lifetime spend seeded from a rough heuristic; the ETL
    # transform stage recomputes the true value from transactional data
    # and will typically diverge from this stale CRM figure.
    base_spend = np.where(is_sth, rng.normal(1400, 400, n_customers), rng.normal(220, 180, n_customers))
    lifetime_spend = np.round(np.clip(base_spend, 0, None), 2)

    df = pd.DataFrame({
        "CustomerID": customer_ids,
        "FirstName": first_names,
        "LastName": last_names,
        "Age": ages,
        "Gender": genders,
        "City": cities,
        "State": states,
        "ZipCode": zips,
        "Email": emails,
        "SignupDate": [d.isoformat() for d in signup_dates],
        "SeasonTicketHolder": is_sth,
        "CustomerSegment": segments,
        "LifetimeSpend": lifetime_spend,
        "PreferredSeatSection": preferred_section,
        "FavoriteOpponent": favorite_opponent,
    })
    return df


def _weighted_opponent_probs() -> np.ndarray:
    weights = np.array([3.0 if opp in RIVALS else 1.0 for opp in OPPONENTS])
    return weights / weights.sum()


# --------------------------------------------------------------------------- #
# Marketing campaigns
# --------------------------------------------------------------------------- #
def generate_campaigns() -> pd.DataFrame:
    """Generate the marketing campaign calendar across both seasons."""
    logger.info("Generating marketing campaigns")
    templates = [
        ("Back to Union Field Kickoff", "Email", "General", 0.10),
        ("Student Night Blitz", "Social Media", "Students", 0.35),
        ("Rival Week Flash Sale", "Email", "Existing Fans", 0.20),
        ("Family Sunday Promo", "Direct Mail", "Families", 0.25),
        ("Season Renewal Loyalty Campaign", "Email", "Season Ticket Holders", 0.12),
        ("Flash Friday Discount", "SMS", "General", 0.30),
        ("Summer Social Push", "Social Media", "Young Professionals", 0.15),
        ("Holiday Match Bundle", "Email", "Families", 0.22),
        ("Group Outing Special", "Direct Mail", "Corporate", 0.18),
        ("Text-to-Win SMS Blast", "SMS", "General", 0.15),
        ("Radio Rewind Giveaway", "Radio", "General", 0.10),
        ("Influencer Fan Day", "Influencer", "Young Professionals", 0.20),
        ("New Fan Welcome Offer", "Email", "Lapsed Fans", 0.40),
        ("Playoff Push Email Series", "Email", "Existing Fans", 0.08),
    ]
    n_campaigns = len(templates)
    season1_start = datetime.strptime(SEASONS[0]["start_date"], "%Y-%m-%d").date()
    season2_end = datetime.strptime(SEASONS[-1]["end_date"], "%Y-%m-%d").date()
    total_span = (season2_end - season1_start).days

    rows = []
    for i, (name, ctype, audience, discount) in enumerate(templates):
        start_offset = int((i / n_campaigns) * total_span + rng.integers(-10, 10))
        start = season1_start + timedelta(days=max(0, start_offset))
        duration = int(rng.integers(10, 45))
        end = start + timedelta(days=duration)
        cost = round(float(rng.uniform(800, 15000)), 2)
        rows.append({
            "CampaignID": i + 1,
            "CampaignName": name,
            "CampaignType": ctype,
            "StartDate": start.isoformat(),
            "EndDate": end.isoformat(),
            "Cost": cost,
            "TargetAudience": audience,
            "DiscountPercentage": discount,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Games (schedule, both seasons, home + away)
# --------------------------------------------------------------------------- #
def generate_games() -> pd.DataFrame:
    """Generate the two-season fixture schedule with attendance dynamics."""
    logger.info("Generating game schedule for %d seasons", len(SEASONS))
    all_games = []
    game_id = 1

    for season in SEASONS:
        season_start = datetime.strptime(season["start_date"], "%Y-%m-%d").date()
        season_end = datetime.strptime(season["end_date"], "%Y-%m-%d").date()
        season_span = (season_end - season_start).days

        n_home_league = CFG["schedule"]["home_games_per_season"]
        n_away_league = CFG["schedule"]["away_games_per_season"]
        n_cup = CFG["schedule"]["cup_games_per_season"]

        fixtures = (
            [("Home", "League")] * n_home_league
            + [("Away", "League")] * n_away_league
            + [("Home", "Cup")] * n_cup
        )
        rng.shuffle(fixtures)

        # evenly space fixtures across the season with jitter, then sort
        slot_days = np.sort(rng.choice(season_span, size=len(fixtures), replace=False))
        win_streak = 0

        for slot, (home_away, competition) in zip(slot_days, fixtures):
            game_date = season_start + timedelta(days=int(slot))
            opponent = rng.choice(OPPONENTS)
            is_rival = opponent in RIVALS
            day_of_week = game_date.strftime("%A")
            is_weekend = day_of_week in ("Saturday", "Sunday")

            kickoff = rng.choice(
                ["12:30", "15:00", "17:30", "19:00", "19:45", "20:00"],
                p=[0.12, 0.20, 0.13, 0.20, 0.20, 0.15] if is_weekend else [0.02, 0.05, 0.08, 0.30, 0.35, 0.20],
            )

            month = game_date.month
            if month in (12, 1, 2):
                weather = rng.choice(WEATHER_OPTIONS, p=[0.25, 0.20, 0.25, 0.20, 0.10])
                temperature = int(rng.normal(34, 10))
            elif month in (3, 4, 11):
                weather = rng.choice(WEATHER_OPTIONS, p=[0.35, 0.30, 0.20, 0.05, 0.10])
                temperature = int(rng.normal(52, 8))
            else:  # Aug, Sep, Oct, May
                weather = rng.choice(WEATHER_OPTIONS, p=[0.55, 0.25, 0.05, 0.02, 0.13])
                temperature = int(rng.normal(70, 9))

            promotion_night = bool(rng.random() < (0.32 if not is_weekend else 0.20))
            opponent_ranking = int(rng.integers(1, 21))
            outcome_win_prob = 0.55 - (opponent_ranking - 10) * 0.01  # tougher opponent -> lower win prob
            won = rng.random() < np.clip(outcome_win_prob, 0.2, 0.8)
            current_streak = win_streak
            win_streak = win_streak + 1 if won else 0

            if home_away == "Home":
                capacity = STADIUM_CAPACITY
            else:
                capacity = int(rng.integers(3000, 9000))

            all_games.append({
                "GameID": game_id,
                "Season": season["label"],
                "Date": game_date.isoformat(),
                "Opponent": opponent,
                "Competition": competition,
                "DayOfWeek": day_of_week,
                "KickoffTime": kickoff,
                "Weather": weather,
                "Temperature": temperature,
                "PromotionNight": promotion_night,
                "Capacity": capacity,
                "HomeAway": home_away,
                "OpponentRanking": opponent_ranking,
                "WinStreak": current_streak,
                "_is_rival": is_rival,
                "_is_weekend": is_weekend,
                "_is_holiday": _is_holiday(game_date),
                "_season_idx": season["id"],
            })
            game_id += 1

    games = pd.DataFrame(all_games)
    games = _apply_attendance_model(games)
    return games


def _apply_attendance_model(games: pd.DataFrame) -> pd.DataFrame:
    """Compute fill-rate driven attendance, calibrated to hit the target
    total ticket volume across home games, and a separate, simpler
    attendance figure for away fixtures (their own box office, not ours).
    """
    base_fill = 0.50
    fill = np.full(len(games), base_fill)
    fill *= np.where(games["_is_weekend"], 1.22, 1.0)
    fill *= np.where(games["_is_rival"], 1.45, 1.0)
    fill *= np.where(games["PromotionNight"], 1.18, 1.0)
    weather_mult = games["Weather"].map({"Clear": 1.05, "Cloudy": 1.0, "Rain": 0.86, "Snow": 0.78, "Windy": 0.95})
    fill *= weather_mult.to_numpy()
    fill *= (1 + (10 - games["OpponentRanking"]) * 0.01)
    fill *= (1 + np.minimum(games["WinStreak"], 5) * 0.03)
    fill *= np.where(games["Competition"] == "Cup", 1.15, 1.0)
    fill *= np.where(games["_is_holiday"], 1.20, 1.0)
    fill *= np.where(games["_season_idx"] == 2, 1.08, 1.0)
    fill *= rng.uniform(0.90, 1.10, size=len(games))
    fill = np.clip(fill, 0.15, 1.0)

    is_home = (games["HomeAway"] == "Home").to_numpy()
    home_fill = fill.copy()

    tickets_sold_raw = np.round(home_fill * games["Capacity"]).astype(int)
    home_mask_sum = tickets_sold_raw[is_home].sum()
    target = CFG["data_generation"]["target_total_tickets"]
    scale = target / home_mask_sum if home_mask_sum > 0 else 1.0
    calibrated_fill = np.clip(home_fill * scale, 0.10, 1.0)

    tickets_sold = np.where(is_home, np.round(calibrated_fill * games["Capacity"]), np.nan)

    # Away game attendance: independent, simpler crowd model for context only
    away_fill = np.clip(rng.uniform(0.35, 0.85, size=len(games)) * np.where(games["_is_rival"], 1.2, 1.0), 0.2, 1.0)
    away_attendance = np.round(away_fill * games["Capacity"])

    show_rate = 0.90
    show_rate_arr = np.full(len(games), show_rate)
    show_rate_arr -= np.where(games["Weather"] == "Rain", 0.12, 0)
    show_rate_arr -= np.where(games["Weather"] == "Snow", 0.20, 0)
    show_rate_arr += np.where(games["_is_rival"], 0.04, 0)
    show_rate_arr += np.where(games["Competition"] == "Cup", 0.04, 0)
    show_rate_arr = np.clip(show_rate_arr, 0.65, 0.99)

    home_attendance = np.round(np.where(is_home, tickets_sold, np.nan) * show_rate_arr)
    attendance = np.where(is_home, home_attendance, away_attendance)

    games = games.copy()
    games["TicketsSold"] = tickets_sold  # NaN for away games (not our box office)
    games["Attendance"] = attendance.astype(int)
    games["_show_rate"] = show_rate_arr
    return games


def _enforce_section_capacity(seat_section: np.ndarray) -> np.ndarray:
    """Reassign any tickets that oversell a section's physical seat count.

    Preference-driven assignment (season ticket holders skewing toward
    Premium/Midfield Club) can otherwise request more seats in a section
    than physically exist for a single game. Overflow tickets are moved to
    whichever remaining sections still have open seats, weighted by how
    much capacity they have left.
    """
    counts = {name: 0 for name in SECTION_NAMES}
    final_section = seat_section.copy()
    overflow_idx = []

    for i, sec in enumerate(seat_section):
        if counts[sec] < SECTION_CAPACITY_ABS[sec]:
            counts[sec] += 1
        else:
            overflow_idx.append(i)

    for i in overflow_idx:
        remaining = {s: SECTION_CAPACITY_ABS[s] - counts[s] for s in SECTION_NAMES if SECTION_CAPACITY_ABS[s] - counts[s] > 0}
        if not remaining:
            break  # total demand exceeds stadium capacity; leave as-is (shouldn't happen)
        secs = list(remaining.keys())
        weights = np.array(list(remaining.values()), dtype=float)
        chosen = rng.choice(secs, p=weights / weights.sum())
        final_section[i] = chosen
        counts[chosen] += 1

    return final_section


# --------------------------------------------------------------------------- #
# Ticket sales (fact table) — only generated for HOME games
# --------------------------------------------------------------------------- #
def generate_ticket_sales(customers: pd.DataFrame, campaigns: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Generate one row per sold seat for every home fixture."""
    logger.info("Generating ticket sales fact table")
    home_games = games[games["HomeAway"] == "Home"].copy()
    season_starts = {s["label"]: datetime.strptime(s["start_date"], "%Y-%m-%d").date() for s in SEASONS}

    customer_ids = customers["CustomerID"].to_numpy()
    is_sth = customers["SeasonTicketHolder"].to_numpy()
    fav_opponent = customers["FavoriteOpponent"].to_numpy()
    preferred_section = customers["PreferredSeatSection"].to_numpy()
    ages = customers["Age"].to_numpy()
    segment = customers["CustomerSegment"].to_numpy()

    # Season-ticket renewal: a season ticket holder isn't guaranteed to come
    # back next season. ~93% renew; the rest lapse into occasional buyers,
    # matching typical pro-sports season-ticket retention.
    season2_label = SEASONS[-1]["label"]
    sth_renewed = np.ones(len(customer_ids), dtype=bool)
    sth_idx = np.where(is_sth)[0]
    sth_renewed[sth_idx] = rng.random(len(sth_idx)) < 0.93
    is_sth_season2 = is_sth & sth_renewed

    base_weight_by_season = {
        SEASONS[0]["label"]: np.select(
            [is_sth, segment == "Frequent Attendee", segment == "Occasional Fan", segment == "New Fan"],
            [50.0, 10.0, 3.0, 2.0],
            default=1.0,
        ),
        season2_label: np.select(
            [is_sth_season2, is_sth & ~sth_renewed, segment == "Frequent Attendee",
             segment == "Occasional Fan", segment == "New Fan"],
            [50.0, 4.0, 10.0, 3.0, 2.0],
            default=1.0,
        ),
    }
    effective_is_sth_by_season = {
        SEASONS[0]["label"]: is_sth,
        season2_label: is_sth_season2,
    }

    ticket_id = 1
    all_rows = []

    for _, game in home_games.iterrows():
        n_tickets = int(game["TicketsSold"]) if not np.isnan(game["TicketsSold"]) else 0
        if n_tickets <= 0:
            continue

        effective_is_sth = effective_is_sth_by_season[game["Season"]]
        weight = base_weight_by_season[game["Season"]].copy()
        weight = np.where(fav_opponent == game["Opponent"], weight * 3.0, weight)
        probs = weight / weight.sum()

        buyer_idx = rng.choice(len(customer_ids), size=n_tickets, replace=True, p=probs)
        buyers = customer_ids[buyer_idx]
        buyer_is_sth = effective_is_sth[buyer_idx]
        buyer_age = ages[buyer_idx]
        buyer_pref_section = preferred_section[buyer_idx]

        # Seat section: STH sit in their preferred section 80% of the time
        random_section = rng.choice(SECTION_NAMES, size=n_tickets, p=SECTION_CAPACITY_SHARE)
        use_pref = rng.random(n_tickets) < np.where(buyer_is_sth, 0.80, 0.25)
        seat_section = np.where(use_pref, buyer_pref_section, random_section)
        seat_section = _enforce_section_capacity(seat_section)

        # Ticket type
        ticket_type = np.full(n_tickets, "Individual Game", dtype=object)
        ticket_type = np.where(buyer_is_sth, "Season", ticket_type)
        is_student_age = buyer_age < 24
        student_section = seat_section == "Student Section"
        ticket_type = np.where((~buyer_is_sth) & is_student_age & student_section, "Student", ticket_type)
        group_roll = rng.random(n_tickets) < 0.08
        ticket_type = np.where((~buyer_is_sth) & group_roll, "Group", ticket_type)
        comp_roll = rng.random(n_tickets) < 0.015
        ticket_type = np.where((~buyer_is_sth) & comp_roll, "Comp", ticket_type)

        # Purchase channel
        channel = np.empty(n_tickets, dtype=object)
        season_mask = ticket_type == "Season"
        channel[season_mask] = "Season Ticket Portal"
        non_season = ~season_mask
        channel[non_season] = rng.choice(
            ["Website", "Mobile App", "Box Office", "Phone", "Third-Party Resale"],
            size=non_season.sum(), p=[0.35, 0.32, 0.15, 0.06, 0.12],
        )

        # Purchase date
        game_date = datetime.strptime(game["Date"], "%Y-%m-%d").date()
        season_start = season_starts[game["Season"]]
        purchase_date = np.empty(n_tickets, dtype=object)
        for i in range(n_tickets):
            if ticket_type[i] == "Season":
                offset = int(rng.integers(0, 45))
                purchase_date[i] = (season_start - timedelta(days=offset)).isoformat()
            else:
                lookback = min(90, (game_date - season_start).days + 30)
                lookback = max(lookback, 1)
                days_before = int(rng.triangular(0, lookback * 0.15, lookback))
                purchase_date[i] = (game_date - timedelta(days=days_before)).isoformat()

        # Campaign attribution (~35% of non-season tickets)
        campaign_id = np.full(n_tickets, np.nan)
        attribution_roll = rng.random(n_tickets) < np.where(season_mask, 0.05, 0.35)
        camp_starts = pd.to_datetime(campaigns["StartDate"]).to_numpy()
        camp_ends = pd.to_datetime(campaigns["EndDate"]).to_numpy()
        camp_ids = campaigns["CampaignID"].to_numpy()
        for i in np.where(attribution_roll)[0]:
            pdate = np.datetime64(purchase_date[i])
            active = camp_ids[(camp_starts <= pdate) & (camp_ends >= pdate)]
            if len(active) > 0:
                campaign_id[i] = rng.choice(active)

        # Pricing
        base_price = np.array([SECTION_BASE_PRICE[s] for s in seat_section])
        demand_surge = 1.10 if (game["_is_rival"] or game["Competition"] == "Cup") else 1.0
        priced_base = base_price * demand_surge

        discount_pct = np.zeros(n_tickets)
        discount_pct = np.where(ticket_type == "Student", discount_pct + 0.40, discount_pct)
        discount_pct = np.where(ticket_type == "Group", discount_pct + 0.15, discount_pct)
        discount_pct = np.where(ticket_type == "Season", discount_pct + 0.18, discount_pct)
        discount_pct = np.where(ticket_type == "Comp", 1.0, discount_pct)
        camp_discount = campaigns.set_index("CampaignID")["DiscountPercentage"].to_dict()
        campaign_discount_arr = np.array([camp_discount.get(cid, 0.0) if not np.isnan(cid) else 0.0 for cid in campaign_id])
        discount_pct = np.clip(discount_pct + campaign_discount_arr, 0, 1.0)

        discount_amt = np.round(priced_base * discount_pct, 2)
        price_paid = np.round(priced_base - discount_amt, 2)
        price_paid = np.clip(price_paid, 0, None)

        fee_pct = np.select(
            [channel == "Third-Party Resale", channel == "Website", channel == "Mobile App"],
            [0.18, 0.10, 0.10],
            default=0.03,
        )
        fees = np.where(ticket_type == "Comp", 0.0, np.round(price_paid * fee_pct, 2))
        revenue = np.round(price_paid + fees, 2)

        # Payment method
        payment_method = np.empty(n_tickets, dtype=object)
        payment_method[season_mask] = rng.choice(
            ["Season Payment Plan", "Credit Card"], size=season_mask.sum(), p=[0.7, 0.3]
        )
        box_office_mask = (~season_mask) & (channel == "Box Office")
        payment_method[box_office_mask] = rng.choice(
            ["Cash", "Credit Card", "Debit Card"], size=box_office_mask.sum(), p=[0.3, 0.45, 0.25]
        )
        remaining = (~season_mask) & (~box_office_mask)
        payment_method[remaining] = rng.choice(
            ["Credit Card", "Debit Card", "Apple Pay", "PayPal"], size=remaining.sum(), p=[0.40, 0.25, 0.20, 0.15]
        )

        # Attendance / scanning
        n_attended = int(game["Attendance"])
        n_attended = min(n_attended, n_tickets)
        attended = np.zeros(n_tickets, dtype=bool)
        attended_idx = rng.choice(n_tickets, size=n_attended, replace=False)
        attended[attended_idx] = True
        scanned = attended.copy()
        scan_glitch = rng.random(n_tickets) < 0.01
        scanned = np.where(scan_glitch, ~scanned, scanned)

        seat_numbers = [f"{rng.choice(list(string.ascii_uppercase[:12]))}{rng.integers(1, 30)}" for _ in range(n_tickets)]

        game_rows = pd.DataFrame({
            "TicketID": np.arange(ticket_id, ticket_id + n_tickets),
            "CustomerID": buyers,
            "GameID": game["GameID"],
            "CampaignID": campaign_id,
            "PurchaseDate": purchase_date,
            "PurchaseChannel": channel,
            "TicketType": ticket_type,
            "SeatSection": seat_section,
            "SeatNumber": seat_numbers,
            "PricePaid": price_paid,
            "Discount": discount_amt,
            "Fees": fees,
            "Revenue": revenue,
            "PaymentMethod": payment_method,
            "Scanned": scanned,
            "Attended": attended,
        })
        all_rows.append(game_rows)
        ticket_id += n_tickets

    ticket_sales = pd.concat(all_rows, ignore_index=True)
    logger.info("Generated %d ticket sales rows", len(ticket_sales))
    return ticket_sales


# --------------------------------------------------------------------------- #
# Merchandise
# --------------------------------------------------------------------------- #
def generate_merchandise(ticket_sales: pd.DataFrame) -> pd.DataFrame:
    """Generate concession/merch spend for a subset of attendees."""
    logger.info("Generating merchandise transactions")
    attended = ticket_sales[ticket_sales["Attended"]][["CustomerID", "GameID"]].reset_index(drop=True)
    buys = rng.random(len(attended)) < 0.40
    buyers = attended[buys].reset_index(drop=True)

    categories = list(MERCH_CATEGORIES.keys())
    rows = []
    for _, row in buyers.iterrows():
        n_items = 1 if rng.random() > 0.15 else 2
        chosen_categories = rng.choice(categories, size=n_items, replace=False)
        for cat in chosen_categories:
            base = MERCH_CATEGORIES[cat]
            amount = round(max(2.0, rng.normal(base, base * 0.25)), 2)
            rows.append({
                "CustomerID": row["CustomerID"],
                "GameID": row["GameID"],
                "Category": cat,
                "AmountSpent": amount,
            })
    merch = pd.DataFrame(rows)
    logger.info("Generated %d merchandise rows", len(merch))
    return merch


# --------------------------------------------------------------------------- #
# Data quality corruption (intentional, to be caught by validate.py/clean.py)
# --------------------------------------------------------------------------- #
def _random_case(value: str) -> str:
    choice = rng.integers(0, 3)
    if choice == 0:
        return str(value).upper()
    if choice == 1:
        return str(value).lower()
    return str(value).title()


def corrupt_customers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    n = len(df)

    # Missing values
    for col, frac in [("Email", 0.02), ("Age", 0.03), ("City", 0.01), ("PreferredSeatSection", 0.02)]:
        idx = rng.choice(n, size=int(n * frac), replace=False)
        df.loc[idx, col] = np.nan

    # Malformed ZIPs
    zip_idx = rng.choice(n, size=int(n * 0.03), replace=False)
    zip_styles = rng.integers(0, 3, size=len(zip_idx))
    for i, style in zip(zip_idx, zip_styles):
        if style == 0:
            df.loc[i, "ZipCode"] = str(df.loc[i, "ZipCode"])[:3]
        elif style == 1:
            df.loc[i, "ZipCode"] = "N/A"
        else:
            df.loc[i, "ZipCode"] = str(df.loc[i, "ZipCode"]) + "-XX"

    # Inconsistent capitalization
    case_idx = rng.choice(n, size=int(n * 0.08), replace=False)
    for col in ("City", "State"):
        for i in case_idx:
            df.loc[i, col] = _random_case(df.loc[i, col])

    # Duplicate customer rows (CRM dupes)
    dup_idx = rng.choice(n, size=int(n * 0.01), replace=False)
    dup_rows = df.loc[dup_idx].copy()
    df = pd.concat([df, dup_rows], ignore_index=True)

    return df


def corrupt_games(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    n = len(df)

    # Missing weather/temperature readings
    for col, frac in [("Weather", 0.02), ("Temperature", 0.02)]:
        idx = rng.choice(n, size=int(n * frac), replace=False)
        df.loc[idx, col] = np.nan

    # Mixed date formats (simulate manual scheduling entries from ops staff)
    fmt_idx = rng.choice(n, size=int(n * 0.05), replace=False)
    for i in fmt_idx:
        d = datetime.strptime(df.loc[i, "Date"], "%Y-%m-%d").date()
        style = rng.integers(0, 3)
        if style == 0:
            df.loc[i, "Date"] = d.strftime("%m/%d/%Y")
        elif style == 1:
            df.loc[i, "Date"] = d.strftime("%B %d, %Y")
        # style 2 leaves ISO format as-is

    # Inconsistent capitalization on categorical text
    case_idx = rng.choice(n, size=int(n * 0.05), replace=False)
    for col in ("Weather", "DayOfWeek", "Competition"):
        for i in case_idx:
            if pd.notna(df.loc[i, col]):
                df.loc[i, col] = _random_case(df.loc[i, col])

    return df


def corrupt_ticket_sales(df: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    n = len(df)
    game_dates = games.set_index("GameID")["Date"].to_dict()

    # Missing values
    for col, frac in [("Discount", 0.02), ("Fees", 0.02), ("CampaignID", 0.0), ("PaymentMethod", 0.01)]:
        if frac == 0:
            continue
        idx = rng.choice(n, size=int(n * frac), replace=False)
        df.loc[idx, col] = np.nan

    # Negative prices (data entry errors)
    neg_idx = rng.choice(n, size=int(n * 0.005), replace=False)
    df.loc[neg_idx, "PricePaid"] = -df.loc[neg_idx, "PricePaid"].abs()
    df.loc[neg_idx, "Revenue"] = -df.loc[neg_idx, "Revenue"].abs()

    # Purchase dates after the game date (impossible / clock skew errors)
    bad_date_idx = rng.choice(n, size=int(n * 0.01), replace=False)
    for i in bad_date_idx:
        gdate_str = game_dates.get(df.loc[i, "GameID"])
        if gdate_str is None:
            continue
        try:
            gdate = datetime.strptime(gdate_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        df.loc[i, "PurchaseDate"] = (gdate + timedelta(days=int(rng.integers(1, 10)))).isoformat()

    # Inconsistent capitalization
    case_idx = rng.choice(n, size=int(n * 0.06), replace=False)
    for col in ("PurchaseChannel", "TicketType", "SeatSection", "PaymentMethod"):
        for i in case_idx:
            if pd.notna(df.loc[i, col]):
                df.loc[i, col] = _random_case(df.loc[i, col])

    # Duplicate ticket rows
    dup_idx = rng.choice(n, size=int(n * 0.015), replace=False)
    dup_rows = df.loc[dup_idx].copy()
    df = pd.concat([df, dup_rows], ignore_index=True)

    return df


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main() -> None:
    raw_dir = resolve_path(CFG["paths"]["raw_dir"])
    raw_dir.mkdir(parents=True, exist_ok=True)

    customers = generate_customers(CFG["data_generation"]["n_customers"])
    campaigns = generate_campaigns()
    games = generate_games()
    ticket_sales = generate_ticket_sales(customers, campaigns, games)
    merchandise = generate_merchandise(ticket_sales)

    games_public = games.drop(columns=[c for c in games.columns if c.startswith("_")])

    customers = corrupt_customers(customers)
    games_public = corrupt_games(games_public)
    ticket_sales = corrupt_ticket_sales(ticket_sales, games_public)

    customers.to_csv(raw_dir / "customers.csv", index=False)
    campaigns.to_csv(raw_dir / "marketing_campaigns.csv", index=False)
    games_public.to_csv(raw_dir / "games.csv", index=False)
    ticket_sales.to_csv(raw_dir / "ticket_sales.csv", index=False)
    merchandise.to_csv(raw_dir / "merchandise.csv", index=False)

    logger.info("Raw data written to %s", raw_dir)
    logger.info(
        "Row counts -> customers: %d, campaigns: %d, games: %d, ticket_sales: %d, merchandise: %d",
        len(customers), len(campaigns), len(games_public), len(ticket_sales), len(merchandise),
    )


if __name__ == "__main__":
    main()
