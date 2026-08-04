"""
build_gold.py
-------------
Builds the Gold star-schema warehouse from Silver:
  1. (Re)create the Gold schema from schema_gold.sql
  2. Populate dim_date from the actual date range in silver.games
  3. Populate dim_players, dim_clubs, dim_competitions from Silver
  4. Populate fact_appearances by joining silver.appearances ->
     games (for date + competition) -> players -> clubs

Run AFTER migrate_to_silver.py has completed.
"""
import os
import sys
import logging

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "bronze"))
from _common import get_connection  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "schema_gold.sql")


def build_schema(conn):
    """Drop and recreate all Gold tables from schema_gold.sql."""
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    logger.info("Gold schema created")


def build_dim_date(conn):
    """Generate one row per calendar day between min and max game date."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO gold.dim_date
                (date_id, full_date, day, month, month_name,
                 quarter, year, day_of_week, day_name, is_weekend)
            SELECT
                TO_CHAR(d, 'YYYYMMDD')::INTEGER,
                d,
                EXTRACT(DAY FROM d)::INTEGER,
                EXTRACT(MONTH FROM d)::INTEGER,
                TO_CHAR(d, 'Month'),
                EXTRACT(QUARTER FROM d)::INTEGER,
                EXTRACT(YEAR FROM d)::INTEGER,
                EXTRACT(DOW FROM d)::INTEGER,
                TO_CHAR(d, 'Day'),
                EXTRACT(DOW FROM d) IN (0, 6)
            FROM generate_series(
                (SELECT MIN(date) FROM silver.games),
                (SELECT MAX(date) FROM silver.games),
                '1 day'::interval
            ) AS d;
        """)
        n = cur.rowcount
    conn.commit()
    logger.info(f"gold.dim_date: {n:,} rows")


def build_dim_competitions(conn):
    """Copy competitions from Silver to Gold."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO gold.dim_competitions
                (competition_id, name, type, sub_type, confederation, country_name)
            SELECT competition_id, name, type, sub_type, confederation, country_name
            FROM silver.competitions;
        """)
        n = cur.rowcount
    conn.commit()
    logger.info(f"gold.dim_competitions: {n:,} rows")


def build_dim_clubs(conn):
    """Copy clubs from Silver to Gold."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO gold.dim_clubs
                (club_id, name, competition_id, stadium_name,
                 stadium_seats, squad_size, coach_name)
            SELECT
                club_id, name, domestic_competition_id, stadium_name,
                stadium_seats, squad_size, coach_name
            FROM silver.clubs
            WHERE domestic_competition_id IS NULL
               OR domestic_competition_id IN (SELECT competition_id FROM gold.dim_competitions);
        """)
        n = cur.rowcount
    conn.commit()
    logger.info(f"gold.dim_clubs: {n:,} rows")


def build_dim_players(conn):
    """Copy players from Silver to Gold."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO gold.dim_players
                (player_id, first_name, last_name, position, sub_position,
                 foot, height_in_cm, date_of_birth, country_of_birth, current_club_id)
            SELECT
                p.player_id, p.first_name, p.last_name, p.position, p.sub_position,
                p.foot, p.height_in_cm, p.date_of_birth, p.country_of_birth,
                CASE
                    WHEN EXISTS (SELECT 1 FROM gold.dim_clubs c WHERE c.club_id = p.current_club_id)
                    THEN p.current_club_id
                    ELSE NULL
                END
            FROM silver.players p;
        """)
        n = cur.rowcount
    conn.commit()
    logger.info(f"gold.dim_players: {n:,} rows")


def build_fact_appearances(conn):
    """
    Populate fact_appearances from silver.appearances joined to silver.games.
    Denormalizes season and competition_id from games into the fact table
    so dashboard queries don't need extra JOINs.
    """
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO gold.fact_appearances
                (appearance_id, date_id, player_id, club_id, competition_id,
                 game_id, season, goals, assists, yellow_cards, red_cards, minutes_played)
            SELECT
                a.appearance_id,
                TO_CHAR(g.date, 'YYYYMMDD')::INTEGER AS date_id,
                a.player_id,
                CASE
                    WHEN EXISTS (SELECT 1 FROM gold.dim_clubs c WHERE c.club_id = a.player_club_id)
                    THEN a.player_club_id
                    ELSE NULL
                END AS club_id,
                g.competition_id,
                a.game_id,
                g.season,
                a.goals,
                a.assists,
                a.yellow_cards,
                a.red_cards,
                a.minutes_played
            FROM silver.appearances a
            JOIN silver.games g ON g.game_id = a.game_id
            WHERE g.date IS NOT NULL
              AND EXISTS (SELECT 1 FROM gold.dim_players p WHERE p.player_id = a.player_id);
        """)
        n = cur.rowcount
    conn.commit()
    logger.info(f"gold.fact_appearances: {n:,} rows")


def verify(conn):
    """Sanity check — row counts across all Gold tables."""
    tables = [
        "gold.dim_date",
        "gold.dim_competitions",
        "gold.dim_clubs",
        "gold.dim_players",
        "gold.fact_appearances",
    ]
    with conn.cursor() as cur:
        logger.info("Gold table row counts:")
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM {table};")
            count = cur.fetchone()[0]
            logger.info(f"  {table:<35} {count:>10,} rows")


def main():
    logger.info("Starting Gold warehouse build...")
    conn = get_connection(logger)
    try:
        build_schema(conn)
        build_dim_date(conn)
        build_dim_competitions(conn)
        build_dim_clubs(conn)
        build_dim_players(conn)
        build_fact_appearances(conn)
        verify(conn)
        logger.info("Gold build complete.")
    except Exception:
        logger.exception("Gold build failed")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()