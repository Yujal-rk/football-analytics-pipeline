"""
transform.py -- shapes Silver data into Gold's star schema.

dim_clubs.competition_id and dim_players.current_club_id are NOT
re-validated here: Silver already guarantees any non-null value in
those columns resolves correctly (see migrate_to_silver.py's CASE/EXISTS
fix). Only fact_appearances.club_id (from player_club_id) needs a
defensive check, since it's the one FK Silver deliberately leaves
unvalidated (polymorphic club/national-team reference).
"""
import logging
import pandas as pd

logger = logging.getLogger(__name__)


def build_dim_date(min_date, max_date):
    dates = pd.date_range(start=min_date, end=max_date, freq="D")
    df = pd.DataFrame({"full_date": dates})
    df["date_id"] = df["full_date"].dt.strftime("%Y%m%d").astype(int)
    df["day"] = df["full_date"].dt.day
    df["month"] = df["full_date"].dt.month
    df["month_name"] = df["full_date"].dt.strftime("%B")
    df["quarter"] = df["full_date"].dt.quarter
    df["year"] = df["full_date"].dt.year
    df["day_of_week"] = df["full_date"].dt.dayofweek
    df["day_name"] = df["full_date"].dt.strftime("%A")
    df["is_weekend"] = df["day_of_week"].isin([5, 6])
    return df[["date_id", "full_date", "day", "month", "month_name",
               "quarter", "year", "day_of_week", "day_name", "is_weekend"]]


def transform_dim_competitions(df):
    out = df.copy()
    out["sub_type"] = out["sub_type"].fillna("Unknown")
    out["confederation"] = out["confederation"].fillna("Unknown")
    return out


def transform_dim_clubs(df):
    """No FK re-validation needed -- Silver already guarantees
    competition_id is valid or NULL."""
    out = df.copy()
    out["stadium_name"] = out["stadium_name"].fillna("Unknown")
    out["coach_name"] = out["coach_name"].fillna("Unknown")
    return out


def transform_dim_players(df):
    """No FK re-validation needed -- Silver already guarantees
    current_club_id is valid or NULL."""
    out = df.copy()
    out["foot"] = out["foot"].fillna("Unknown")
    out["position"] = out["position"].fillna("Unknown")
    return out


FACT_COLUMNS = [
    "appearance_id", "date_id", "player_id", "club_id", "competition_id",
    "game_id", "season", "goals", "assists", "yellow_cards", "red_cards",
    "minutes_played",
]


def transform_fact_appearances(appearances_df, games_df, valid_player_ids,
                                valid_club_ids, valid_date_ids):
    if appearances_df.empty:
        logger.info("No appearances extracted -- nothing to transform")
        return pd.DataFrame(columns=FACT_COLUMNS)

    initial_count = len(appearances_df)

    games_slim = games_df[["game_id", "competition_id", "season", "date"]].copy()
    df = appearances_df.merge(games_slim, on="game_id", how="left")

    # date_id and player_id are NOT NULL in gold.fact_appearances -- these
    # rows genuinely cannot be loaded without them, so they're dropped
    # (not nulled), same reasoning as silver.appearances' own NOT NULL FKs.
    missing_date = df["date"].isna()
    if missing_date.any():
        logger.warning(f"{missing_date.sum()} appearance(s) with no matching game date -- skipped")
    df = df[~missing_date]

    df["date_id"] = pd.to_datetime(df["date"]).dt.strftime("%Y%m%d").astype(int)
    bad_date = ~df["date_id"].isin(valid_date_ids)
    if bad_date.any():
        logger.warning(f"{bad_date.sum()} appearance(s) with date_id outside dim_date range -- skipped")
    df = df[~bad_date]

    bad_player = ~df["player_id"].isin(valid_player_ids)
    if bad_player.any():
        logger.warning(f"{bad_player.sum()} appearance(s) with unresolvable player_id -- skipped")
    df = df[~bad_player]

    # club_id IS nullable in fact_appearances -- null it out (keep the
    # row) rather than dropping, since player_club_id can legitimately
    # point at a national team ID, not just a club.
    df = df.rename(columns={"player_club_id": "club_id"})
    bad_club = df["club_id"].notna() & ~df["club_id"].isin(valid_club_ids)
    if bad_club.any():
        logger.info(f"{bad_club.sum()} appearance(s) with club_id not in dim_clubs "
                    f"(likely national team IDs, see decisions_log) -- club_id set to NULL")
    df.loc[bad_club, "club_id"] = None

    result = df[FACT_COLUMNS].reset_index(drop=True)
    logger.info(f"Transformed {len(result)} rows, skipped {initial_count - len(result)}")
    return result