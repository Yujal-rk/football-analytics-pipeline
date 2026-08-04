"""
load_clubs.py -- Bronze / raw landing loader for clubs.csv.
See load_competitions.py for the full Bronze design rationale.
"""
import csv
import io
import os
import logging
from _common import get_connection

logger = logging.getLogger(__name__)

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "source", "clubs.csv")
TABLE = "bronze.clubs"

CREATE_TABLE_SQL = f"""
DROP TABLE IF EXISTS {TABLE};

CREATE TABLE {TABLE} (
    club_id                  INTEGER       PRIMARY KEY,
    club_code                VARCHAR(50),
    name                     VARCHAR(100),
    domestic_competition_id  VARCHAR(10),
    total_market_value       VARCHAR(50),
    squad_size                INTEGER,
    average_age                DECIMAL(5, 2),
    foreigners_number          INTEGER,
    foreigners_percentage      DECIMAL(5, 2),
    national_team_players      INTEGER,
    stadium_name                VARCHAR(100),
    stadium_seats                INTEGER,
    net_transfer_record           VARCHAR(50),
    coach_name                     VARCHAR(100),
    last_season                     INTEGER,
    filename                         VARCHAR(255),
    url                               VARCHAR(500)
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
                SELECT name, squad_size, average_age, domestic_competition_id
                FROM {TABLE}
                WHERE squad_size > 0
                ORDER BY squad_size DESC
                LIMIT 10;
            """)
            rows = cur.fetchall()
        logger.info("Top 10 clubs by squad size:")
        for name, squad_size, avg_age, comp_id in rows:
            logger.info(f"  {name:<30} squad={squad_size:>3} age={avg_age:>5} comp={comp_id}")
    except Exception as e:
        logger.error(f"Failed to run verification query: {e}")
        raise


def main():
    logger.info("Starting clubs Bronze loader...")
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
