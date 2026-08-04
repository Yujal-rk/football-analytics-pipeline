"""
load_appearances.py -- Bronze / raw landing loader for appearances.csv.

This is the table the whole Bronze pattern was worked out on:
  - appearance_id is a string ("gameid_playerid"), not an integer -> VARCHAR PK
  - Only appearance_id is constrained; everything else is nullable
  - 3 rows in the source have minutes_played > 120 (135, 135, 148) -- these
    are known data quality issues, investigated and confirmed as source
    errors. They are intentionally NOT filtered here (Bronze keeps
    everything as-is); the Silver quality gate is where they get handled.
  - At least one row has a blank player_name -- also left as NULL here.
"""
import csv
import io
import os
import logging
from _common import get_connection

logger = logging.getLogger(__name__)

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "source", "appearances.csv")
TABLE = "bronze.appearances"

CREATE_TABLE_SQL = f"""
DROP TABLE IF EXISTS {TABLE};

CREATE TABLE {TABLE} (
    appearance_id           VARCHAR(20)   PRIMARY KEY,
    game_id                 INTEGER,
    player_id               INTEGER,
    player_club_id          INTEGER,
    player_current_club_id  INTEGER,
    date                    DATE,
    player_name             VARCHAR(100),
    competition_id          VARCHAR(10),
    yellow_cards            INTEGER,
    red_cards               INTEGER,
    goals                   INTEGER,
    assists                 INTEGER,
    minutes_played          INTEGER
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
                SELECT player_name, SUM(goals) AS total_goals, COUNT(*) AS appearances
                FROM {TABLE}
                WHERE goals > 0
                GROUP BY player_name
                ORDER BY total_goals DESC
                LIMIT 10;
            """)
            rows = cur.fetchall()
        logger.info("Top 10 scorers:")
        for player_name, total_goals, appearance_count in rows:
            logger.info(f"  {player_name:<25} {total_goals:>6} goals in {appearance_count:>4} appearances")
    except Exception as e:
        logger.error(f"Failed to run verification query: {e}")
        raise


def main():
    logger.info("Starting appearances Bronze loader...")
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
