"""
load_competitions.py
---------------------
Bronze / raw landing loader for competitions.csv.

Bronze layer philosophy (decided during mentoring session):
  - Mirror the source CSV as-is.
  - Only the natural primary key is constrained (structural identity).
  - No business-rule constraints (NOT NULL / CHECK) — those belong in Silver.
  - No filtering, no value substitution — whatever the source has, we keep.
  - Uses csv.reader + tab-delimited COPY so quoted fields with commas
    (club/competition names) never break column alignment.
"""
import csv
import io
import os
import logging
from _common import get_connection

logger = logging.getLogger(__name__)

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "source", "competitions.csv")
TABLE = "bronze.competitions"

CREATE_TABLE_SQL = f"""
DROP TABLE IF EXISTS {TABLE};

CREATE TABLE {TABLE} (
    competition_id           VARCHAR(10)   PRIMARY KEY,
    competition_code         VARCHAR(50),
    name                     VARCHAR(100),
    sub_type                 VARCHAR(50),
    type                     VARCHAR(50),
    country_id               INTEGER,
    country_name             VARCHAR(100),
    domestic_league_code     VARCHAR(10),
    confederation             VARCHAR(50),
    total_clubs               INTEGER,
    url                       VARCHAR(500)
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
                SELECT confederation, type, COUNT(*) AS count
                FROM {TABLE}
                GROUP BY confederation, type
                ORDER BY confederation, type;
            """)
            rows = cur.fetchall()
        logger.info("Competitions by confederation and type:")
        for confederation, comp_type, count in rows:
            logger.info(f"  {confederation:<15} {comp_type:<25} count={count}")
    except Exception as e:
        logger.error(f"Failed to run verification query: {e}")
        raise


def main():
    logger.info("Starting competitions Bronze loader...")
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
