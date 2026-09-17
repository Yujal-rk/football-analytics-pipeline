"""
pipeline.py -- Silver -> Gold orchestrator.
Run with: python pipeline.py   (from inside gold/)
"""
import os
import sys
import time
import logging
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "bronze", ".env"))

sys.path.append(os.path.dirname(__file__))
from _common import get_connection
from extract import (
    extract_competitions, extract_clubs, extract_players,
    extract_games, extract_appearances_chunked, get_date_range
)
from transform import (
    build_dim_date, transform_dim_competitions, transform_dim_clubs,
    transform_dim_players, transform_fact_appearances
)
from load import (
    load_dim_date, load_dim_competitions, load_dim_clubs,
    load_dim_players, load_fact_appearances
)
from quality import run_quality_checks, DataQualityError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "schema_gold.sql")


def build_schema(conn):
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    logger.info("Gold schema created")


def main():
    logger.info("Starting Silver -> Gold pipeline...")
    conn = get_connection(logger)
    try:
        build_schema(conn)

        t0 = time.time()
        min_date, max_date = get_date_range(conn)
        date_df = build_dim_date(min_date, max_date)
        load_dim_date(conn, date_df)
        logger.info(f"dim_date done in {time.time() - t0:.2f}s")

        t0 = time.time()
        comp_df = transform_dim_competitions(extract_competitions(conn))
        load_dim_competitions(conn, comp_df)
        logger.info(f"dim_competitions done in {time.time() - t0:.2f}s")

        t0 = time.time()
        clubs_df = transform_dim_clubs(extract_clubs(conn))
        load_dim_clubs(conn, clubs_df)
        logger.info(f"dim_clubs done in {time.time() - t0:.2f}s")

        t0 = time.time()
        players_df = transform_dim_players(extract_players(conn))
        load_dim_players(conn, players_df)
        logger.info(f"dim_players done in {time.time() - t0:.2f}s")

        t0 = time.time()
        games_df = extract_games(conn)
        valid_player_ids = set(players_df["player_id"])
        valid_club_ids = set(clubs_df["club_id"])
        valid_date_ids = set(date_df["date_id"])

        # fact_appearances is ~1.9M rows -- too large to hold as one
        # DataFrame on this machine, so it's streamed in chunks. Every
        # chunk is loaded with commit=False, and we only conn.commit()
        # once ALL chunks have passed transform + quality checks --
        # so the table ends up either fully loaded or untouched, never
        # half-loaded, if something fails partway through.
        total_rows = 0
        chunk_num = 0
        try:
            for appearances_chunk in extract_appearances_chunked(conn):
                chunk_num += 1

                fact_chunk = transform_fact_appearances(
                    appearances_chunk, games_df,
                    valid_player_ids=valid_player_ids,
                    valid_club_ids=valid_club_ids,
                    valid_date_ids=valid_date_ids,
                )

                run_quality_checks(fact_chunk)

                load_fact_appearances(conn, fact_chunk, commit=False)
                total_rows += len(fact_chunk)
                logger.info(f"Chunk {chunk_num}: {len(fact_chunk)} rows loaded (running total: {total_rows})")

            conn.commit()
            logger.info(
                f"fact_appearances done in {time.time() - t0:.2f}s "
                f"({total_rows} rows across {chunk_num} chunks, committed)"
            )
        except DataQualityError as e:
            conn.rollback()
            logger.error(f"QUALITY GATE FAILED on chunk {chunk_num}: {e} -- all chunks rolled back")
            sys.exit(1)
        except Exception:
            conn.rollback()
            logger.error(f"fact_appearances load failed on chunk {chunk_num} -- all chunks rolled back")
            raise

        logger.info("Gold pipeline complete.")
    except Exception:
        logger.exception("Gold pipeline failed")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()