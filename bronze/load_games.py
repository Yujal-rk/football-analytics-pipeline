"""
load_games.py -- Bronze / raw landing loader for games.csv.
See load_competitions.py for the full Bronze design rationale.
"""
import csv
import io
import os
import logging
from _common import get_connection

logger = logging.getLogger(__name__)

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "source", "games.csv")
TABLE = "bronze.games"

CREATE_TABLE_SQL = f"""
DROP TABLE IF EXISTS {TABLE};

CREATE TABLE {TABLE} (
    game_id                    INTEGER       PRIMARY KEY,
    competition_id             VARCHAR(10),
    season                     INTEGER,
    round                      VARCHAR(50),
    date                       DATE,
    home_club_id               INTEGER,
    away_club_id               INTEGER,
    home_club_goals            INTEGER,
    away_club_goals            INTEGER,
    home_club_position         INTEGER,
    away_club_position         INTEGER,
    home_club_manager_name     VARCHAR(100),
    away_club_manager_name     VARCHAR(100),
    stadium                    VARCHAR(100),
    attendance                 INTEGER,
    referee                    VARCHAR(100),
    url                        VARCHAR(500),
    home_club_formation        VARCHAR(100),
    away_club_formation        VARCHAR(100),
    home_club_name              VARCHAR(100),
    away_club_name              VARCHAR(100),
    aggregate                    VARCHAR(50),
    competition_type              VARCHAR(50)
);
"""


def create_table(conn):
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
        conn.commit()
        logger.info(f"Table '{TABLE}' created successfully")
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to create table: {e}")
        raise


def load_csv(conn, csv_path):
    try:
        with conn.cursor() as cur:
            with open(csv_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                next(reader)
                cleaned = io.StringIO()
                writer = csv.writer(cleaned, delimiter="\t")
                for fields in reader:
                    writer.writerow(fields)
                cleaned.seek(0)
                cur.copy_expert(
                    sql=f"COPY {TABLE} FROM STDIN WITH (FORMAT text, DELIMITER E'\\t', NULL '')",
                    file=cleaned
                )
            row_count = cur.rowcount
        conn.commit()
        logger.info(f"Loaded {row_count:,} rows into '{TABLE}'")
        return row_count
    except FileNotFoundError:
        logger.error(f"CSV file not found: {csv_path}")
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to load CSV: {e}")
        raise


def verify(conn):
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT competition_id, season, COUNT(*) AS game_count
                FROM {TABLE}
                GROUP BY competition_id, season
                ORDER BY season DESC, competition_id
                LIMIT 15;
            """)
            rows = cur.fetchall()
        logger.info("Sample: games by competition and season:")
        for comp_id, season, game_count in rows:
            logger.info(f"  {comp_id:<10} season {season} count={game_count:>5}")
    except Exception as e:
        logger.error(f"Failed to run verification query: {e}")
        raise


def main():
    logger.info("Starting games Bronze loader...")
    conn = get_connection(logger)
    try:
        create_table(conn)
        load_csv(conn, CSV_PATH)
        verify(conn)
    finally:
        conn.close()
    logger.info("Load complete")


if __name__ == "__main__":
    main()
