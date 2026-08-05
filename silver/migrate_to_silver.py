"""
migrate_to_silver.py
---------------------
Orchestrates the Bronze -> Silver step:
  1. (Re)build the Silver schema from schema_silver.sql
  2. Run the quality gate against Bronze data (measures/logs issues,
     does not filter anything itself -- see quality.py)
  3. INSERT INTO ... SELECT each Silver table from its Bronze source.

FK handling policy (important): when a row's foreign key doesn't resolve
against the parent table (e.g. a player's current_club_id pointing at a
club that doesn't exist), we KEEP the row and set only that column to
NULL -- we do NOT drop the row. Dropping rows over an unresolved FK
cascades: a dropped player takes every one of their appearances with it,
a dropped game takes every appearance in that game with it. Since
appearances is the fact table this whole project analyzes, preserving
rows and nulling the bad FK is far less destructive than mass-deleting
performance history over an unrelated club/competition data gap.

Scope note: national_teams was deliberately scoped OUT of this project
(see docs/decisions_log.md). players.current_national_team_id,
games.home_club_id/away_club_id, and appearances.player_club_id are all
migrated as plain, unconstrained integers -- some of these values
reference national teams rather than clubs and will not resolve against
silver.clubs. This is a known, documented limitation, not a bug.

Run AFTER all 5 Bronze loaders (bronze/load_*.py) have completed.
"""
import os
import sys
import logging
import psycopg2

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "bronze"))
from _common import get_connection  # noqa: E402
from quality import run_quality_checks, DataQualityError  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "schema_silver.sql")


def build_schema(conn):
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    logger.info("Silver schema created")


def migrate_competitions(conn):
    """silver.competitions: competition_id, name, sub_type, type,
    country_name, domestic_league_code, confederation. country_id
    dropped -- no lookup table available for it. No FKs to worry
    about here except the self-referencing domestic_league_code,
    which is DEFERRABLE (checked at commit time), so no CASE needed."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO silver.competitions
                (competition_id, name, sub_type, type,
                 country_name, domestic_league_code, confederation)
            SELECT
                competition_id,
                name,
                NULLIF(sub_type, ''),
                NULLIF(type, ''),
                NULLIF(country_name, ''),
                NULLIF(domestic_league_code, ''),
                NULLIF(confederation, '')
            FROM bronze.competitions
            WHERE competition_id IS NOT NULL;
        """)
        n = cur.rowcount
    conn.commit()
    logger.info(f"silver.competitions: {n:,} rows migrated")


def migrate_clubs(conn):
    """silver.clubs: club_id, name, domestic_competition_id, squad_size,
    foreigners_number, national_team_players, stadium_name, stadium_seats,
    coach_name, last_season. total_market_value/average_age/etc dropped
    (out of scope for player-performance analysis).

    FIXED: previously dropped the whole club row if domestic_competition_id
    didn't resolve against silver.competitions. Now keeps the club and
    nulls only that column when it doesn't resolve."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO silver.clubs
                (club_id, name, domestic_competition_id, squad_size,
                 foreigners_number, national_team_players, stadium_name,
                 stadium_seats, coach_name, last_season)
            SELECT
                c.club_id,
                c.name,
                CASE WHEN EXISTS (
                        SELECT 1 FROM silver.competitions comp
                        WHERE comp.competition_id = NULLIF(c.domestic_competition_id, '')
                     )
                     THEN NULLIF(c.domestic_competition_id, '')
                     ELSE NULL END,
                c.squad_size,
                c.foreigners_number,
                c.national_team_players,
                NULLIF(c.stadium_name, ''),
                c.stadium_seats,
                NULLIF(c.coach_name, ''),
                c.last_season
            FROM bronze.clubs c
            WHERE c.club_id IS NOT NULL;
        """)
        n = cur.rowcount
    conn.commit()
    logger.info(f"silver.clubs: {n:,} rows migrated")


def migrate_players(conn):
    """silver.players: player_id, first_name, last_name, last_season,
    current_club_id, country_of_birth, date_of_birth, position,
    sub_position, foot, height_in_cm, international_caps,
    international_goals, current_national_team_id.
    current_national_team_id kept as a PLAIN unconstrained integer --
    national_teams table was scoped out, so no FK is possible.

    FIXED: previously dropped the whole player row if current_club_id
    didn't resolve against silver.clubs -- this was the biggest source
    of cascading data loss (3,792 players dropped, taking thousands of
    their appearances down with them). Now keeps the player and nulls
    only current_club_id when it doesn't resolve."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO silver.players
                (player_id, first_name, last_name, last_season, current_club_id,
                 country_of_birth, date_of_birth, position, sub_position, foot,
                 height_in_cm, international_caps, international_goals,
                 current_national_team_id)
            SELECT
                p.player_id,
                NULLIF(p.first_name, ''),
                NULLIF(p.last_name, ''),
                NULLIF(p.last_season, '')::INTEGER,
                CASE WHEN EXISTS (
                        SELECT 1 FROM silver.clubs c WHERE c.club_id = p.current_club_id
                     )
                     THEN p.current_club_id
                     ELSE NULL END,
                NULLIF(p.country_of_birth, ''),
                NULLIF(p.date_of_birth, '')::DATE,
                NULLIF(p.position, ''),
                NULLIF(p.sub_position, ''),
                NULLIF(p.foot, ''),
                p.height_in_cm,
                NULLIF(p.international_caps, '')::INTEGER,
                NULLIF(p.international_goals, '')::INTEGER,
                NULLIF(p.current_national_team_id, '')::INTEGER
            FROM bronze.players p
            WHERE p.player_id IS NOT NULL;
        """)
        n = cur.rowcount
    conn.commit()
    logger.info(f"silver.players: {n:,} rows migrated")


def migrate_games(conn):
    """silver.games: game_id, competition_id, season, round, date,
    home_club_id, away_club_id, home_club_goals, away_club_goals,
    home_club_position, away_club_position, home_club_manager_name,
    away_club_manager_name, stadium, attendance, referee.
    home_club_id/away_club_id kept as PLAIN unconstrained integers --
    they may point to a club OR a national team (polymorphic reference,
    no single FK can express that); resolve via a join through
    competitions.type at query time if needed.
    competition_type NOT stored -- derivable from competitions.type,
    storing it again would be redundant.

    FIXED: previously dropped the whole game row if competition_id
    didn't resolve against silver.competitions (1,214 games lost, plus
    every appearance in those games). Now keeps the game and nulls only
    competition_id when it doesn't resolve."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO silver.games
                (game_id, competition_id, season, round, date, home_club_id,
                 away_club_id, home_club_goals, away_club_goals, home_club_position,
                 away_club_position, home_club_manager_name, away_club_manager_name,
                 stadium, attendance, referee)
            SELECT
                g.game_id,
                CASE WHEN EXISTS (
                        SELECT 1 FROM silver.competitions c
                        WHERE c.competition_id = NULLIF(g.competition_id, '')
                     )
                     THEN NULLIF(g.competition_id, '')
                     ELSE NULL END,
                g.season,
                NULLIF(g.round, ''),
                g.date,
                g.home_club_id,
                g.away_club_id,
                g.home_club_goals,
                g.away_club_goals,
                g.home_club_position,
                g.away_club_position,
                NULLIF(g.home_club_manager_name, ''),
                NULLIF(g.away_club_manager_name, ''),
                NULLIF(g.stadium, ''),
                g.attendance,
                NULLIF(g.referee, '')
            FROM bronze.games g
            WHERE g.game_id IS NOT NULL;
        """)
        n = cur.rowcount
    conn.commit()
    logger.info(f"silver.games: {n:,} rows migrated")


def migrate_appearances(conn):
    """
    silver.appearances: appearance_id, game_id, player_id, player_club_id,
    yellow_cards, red_cards, goals, assists, minutes_played.

    game_id and player_id are NOT NULL + FK'd in the Silver schema itself
    (see schema_silver.sql), so unlike clubs/players/games above, an
    appearance genuinely CANNOT exist without a valid game and player --
    there's no sensible "null it out" option here. These EXISTS checks
    are필 still required, but now that migrate_games/migrate_players no
    longer drop rows over unrelated FK issues, far more games and players
    survive into Silver, so far fewer appearances get excluded here as
    a side effect.

    Filters applied:
      - minutes_played must be 0-120 (drops the known bad rows: 135, 135, 148)
      - game_id / player_id must exist in silver.games / silver.players
        (structurally required -- these are NOT NULL FK columns)
    player_club_id kept as a PLAIN unconstrained integer -- same
    polymorphic-reference reasoning as games.home_club_id/away_club_id;
    a small fraction of rows are known not to resolve against
    silver.clubs (measured directly against bronze data), accepted as a
    documented, quantified trade-off rather than dropping the column
    entirely.
    """
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO silver.appearances
                (appearance_id, game_id, player_id, player_club_id,
                 yellow_cards, red_cards, goals, assists, minutes_played)
            SELECT
                a.appearance_id, a.game_id, a.player_id, a.player_club_id,
                COALESCE(a.yellow_cards, 0),
                COALESCE(a.red_cards, 0),
                COALESCE(a.goals, 0),
                COALESCE(a.assists, 0),
                COALESCE(a.minutes_played, 0)
            FROM bronze.appearances a
            WHERE a.game_id IS NOT NULL
              AND a.player_id IS NOT NULL
              AND COALESCE(a.minutes_played, 0) BETWEEN 0 AND 120
              AND EXISTS (SELECT 1 FROM silver.games g WHERE g.game_id = a.game_id)
              AND EXISTS (SELECT 1 FROM silver.players p WHERE p.player_id = a.player_id);
        """)
        n = cur.rowcount
    conn.commit()
    logger.info(f"silver.appearances: {n:,} rows migrated")

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM bronze.appearances WHERE minutes_played > 120")
        excluded = cur.fetchone()[0]
    logger.warning(f"Excluded {excluded} appearances with minutes_played > 120 (data quality)")


def main():
    logger.info("Starting Bronze -> Silver migration...")
    conn = get_connection(logger)
    try:
        build_schema(conn)

        try:
            run_quality_checks(conn)
        except DataQualityError as e:
            logger.error(f"QUALITY GATE FAILED: {e}")
            sys.exit(1)

        migrate_competitions(conn)
        migrate_clubs(conn)
        migrate_players(conn)
        migrate_games(conn)
        migrate_appearances(conn)

        logger.info("Silver migration complete.")
    except Exception:
        logger.exception("Silver migration failed")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()