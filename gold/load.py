"""load.py -- writes transformed DataFrames into the Gold tables."""
import logging
import pandas as pd
from psycopg2.extras import execute_values


logger = logging.getLogger(__name__)


def _records(df: pd.DataFrame) -> list:
    return df.astype(object).where(pd.notnull(df), None).to_dict("records")


def _execute_batch(conn, sql, columns, df: pd.DataFrame, table_name: str):
    if df.empty:
        logger.info(f"No rows to load — skipping {table_name}")
        return
    records = _records(df)
    values = [tuple(r[c] for c in columns) for r in records]
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            before = cur.fetchone()[0]

            execute_values(cur, sql, values, page_size=5000)

            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            after = cur.fetchone()[0]

            logger.info(f"{after - before} new rows inserted to {table_name} ({len(values)} attempted)")
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(str(e))
        raise



def _execute(conn, sql, df: pd.DataFrame, table_name: str):
    if df.empty:
        logger.info(f"No rows to load — skipping {table_name}")
        return
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, _records(df))
            logger.info(f"{cur.rowcount if cur.rowcount != -1 else len(df)} inserted to {table_name}")
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(str(e))
        raise


def load_dim_date(conn, df):
    sql = """
        INSERT INTO gold.dim_date
            (date_id, full_date, day, month, month_name, quarter, year,
             day_of_week, day_name, is_weekend)
        VALUES (%(date_id)s, %(full_date)s, %(day)s, %(month)s, %(month_name)s,
                %(quarter)s, %(year)s, %(day_of_week)s, %(day_name)s, %(is_weekend)s)
        ON CONFLICT (date_id) DO NOTHING
    """
    _execute(conn, sql, df, "dim_date")


def load_dim_competitions(conn, df):
    sql = """
        INSERT INTO gold.dim_competitions
            (competition_id, name, type, sub_type, confederation, country_name)
        VALUES (%(competition_id)s, %(name)s, %(type)s, %(sub_type)s,
                %(confederation)s, %(country_name)s)
        ON CONFLICT (competition_id) DO NOTHING
    """
    _execute(conn, sql, df, "dim_competitions")


def load_dim_clubs(conn, df):
    sql = """
        INSERT INTO gold.dim_clubs
            (club_id, name, competition_id, stadium_name, stadium_seats, squad_size, coach_name)
        VALUES (%(club_id)s, %(name)s, %(competition_id)s, %(stadium_name)s,
                %(stadium_seats)s, %(squad_size)s, %(coach_name)s)
        ON CONFLICT (club_id) DO NOTHING
    """
    _execute(conn, sql, df, "dim_clubs")


def load_dim_players(conn, df):
    columns = ["player_id", "first_name", "last_name", "position", "sub_position",
               "foot", "height_in_cm", "date_of_birth", "country_of_birth", "current_club_id"]
    sql = f"""
        INSERT INTO gold.dim_players ({", ".join(columns)})
        VALUES %s
        ON CONFLICT (player_id) DO NOTHING
    """
    _execute_batch(conn, sql.strip(), columns, df, "gold.dim_players")


def load_fact_appearances(conn, df):
    columns = ["appearance_id", "date_id", "player_id", "club_id", "competition_id",
               "game_id", "season", "goals", "assists", "yellow_cards", "red_cards", "minutes_played"]
    sql = f"""
        INSERT INTO gold.fact_appearances ({", ".join(columns)})
        VALUES %s
        ON CONFLICT (appearance_id) DO NOTHING
    """
    _execute_batch(conn, sql.strip(), columns, df, "gold.fact_appearances")