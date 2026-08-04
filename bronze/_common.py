"""
_common.py
----------
Shared connection helper for every Bronze loader.
Reads credentials from .env (see .env.example) instead of hardcoding them.
"""
import os
import logging
import psycopg2
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)

DB_CONFIG = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=os.getenv("DB_PORT", 5432),
    dbname=os.getenv("DB_NAME", "football_db"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", ""),
)


def get_connection(logger):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS bronze;")
        conn.commit()
        logger.info(f"Connected to {DB_CONFIG['dbname']} on {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Failed to connect to database: {e}")
        raise
