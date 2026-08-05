"""
extract.py -- pulls clean data out of Silver for the Gold build.
No cleaning logic here -- Silver already guarantees clubs/players/games
FKs are either valid or NULL (see silver/migrate_to_silver.py). The one
exception is appearances.player_club_id, which is intentionally
unvalidated (polymorphic: can point to a club OR a national team).
"""
import logging
import pandas as pd

logger = logging.getLogger(__name__)


def extract(conn, sql, params=None):
    try:
        df = pd.read_sql_query(sql, conn, params=params)
        logger.info(f"Extracted {len(df)} rows")
        return df
    except Exception as e:
        logger.error(str(e))
        raise


def extract_competitions(conn):
    return extract(conn, """
        SELECT competition_id, name, type, sub_type, confederation, country_name
        FROM silver.competitions
    """)


def extract_clubs(conn):
    return extract(conn, """
        SELECT club_id, name, domestic_competition_id AS competition_id,
               stadium_name, stadium_seats, squad_size, coach_name
        FROM silver.clubs
    """)


def extract_players(conn):
    return extract(conn, """
        SELECT player_id, first_name, last_name, position, sub_position, foot,
               height_in_cm, date_of_birth, country_of_birth, current_club_id
        FROM silver.players
    """)


def extract_games(conn):
    """Needed to give appearances their date/season/competition context."""
    return extract(conn, """
        SELECT game_id, competition_id, season, date
        FROM silver.games
        WHERE date IS NOT NULL
    """)


def extract_appearances(conn):
    return extract(conn, """
        SELECT appearance_id, game_id, player_id, player_club_id,
               yellow_cards, red_cards, goals, assists, minutes_played
        FROM silver.appearances
    """)


def get_date_range(conn):
    df = pd.read_sql_query(
        "SELECT MIN(date) AS min_date, MAX(date) AS max_date FROM silver.games WHERE date IS NOT NULL",
        conn
    )
    return df["min_date"].iloc[0], df["max_date"].iloc[0]