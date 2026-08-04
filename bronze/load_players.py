"""
load_players.py -- Bronze / raw landing loader for players.csv.
See load_competitions.py for the full Bronze design rationale.
"""
import csv
import io
import os
import logging
from _common import get_connection

logger = logging.getLogger(__name__)

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "source", "players.csv")
TABLE = "bronze.players"

CREATE_TABLE_SQL = f"""
DROP TABLE IF EXISTS {TABLE};

CREATE TABLE {TABLE} (
    player_id                              INTEGER       PRIMARY KEY,
    first_name                             VARCHAR(100),
    last_name                              VARCHAR(100),
    name                                   VARCHAR(100),
    last_season                            VARCHAR(10),
    current_club_id                        INTEGER,
    player_code                            VARCHAR(100),
    country_of_birth                       VARCHAR(100),
    city_of_birth                          VARCHAR(100),
    country_of_citizenship                 VARCHAR(100),
    date_of_birth                          VARCHAR(50),
    sub_position                           VARCHAR(50),
    position                               VARCHAR(50),
    foot                                   VARCHAR(20),
    height_in_cm                           INTEGER,
    contract_expiration_date               VARCHAR(50),
    agent_name                             VARCHAR(100),
    image_url                              VARCHAR(500),
    international_caps                     VARCHAR(10),
    international_goals                    VARCHAR(10),
    current_national_team_id               VARCHAR(10),
    url                                    VARCHAR(500),
    current_club_domestic_competition_id   VARCHAR(10),
    current_club_name                      VARCHAR(100),
    market_value_in_eur                    VARCHAR(50),
    highest_market_value_in_eur            VARCHAR(50)
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
                SELECT position, sub_position, COUNT(*) AS player_count
                FROM {TABLE}
                WHERE position IS NOT NULL
                GROUP BY position, sub_position
                ORDER BY player_count DESC
                LIMIT 15;
            """)
            rows = cur.fetchall()
        logger.info("Top 15 player positions by count:")
        for position, sub_position, player_count in rows:
            sub_display = sub_position if sub_position is not None else "-"
            logger.info(f"  {position:<15} {sub_display:<25} count={player_count:>5}")
    except Exception as e:
        logger.error(f"Failed to run verification query: {e}")
        raise


def main():
    logger.info("Starting players Bronze loader...")
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
