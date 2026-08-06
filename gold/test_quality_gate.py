"""
test_quality_gate.py -- standalone script to demonstrate the Gold
quality gate catching bad data, for run2_bad_data.log.
"""
import os
import logging
import pandas as pd
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "bronze", ".env")
load_dotenv(ENV_PATH)

from _common import get_connection
from quality import run_quality_checks, DataQualityError

logging.basicConfig(level=logging.INFO,
                     format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

conn = get_connection(logger)
try:
    df = pd.read_sql_query("SELECT * FROM gold.fact_appearances", conn)
    logger.info(f"Loaded {len(df)} rows from gold.fact_appearances for checking")
    run_quality_checks(df)
    logger.info("Quality gate passed -- no bad data found.")
except DataQualityError as e:
    logger.error(f"QUALITY GATE CAUGHT BAD DATA: {e}")
finally:
    conn.close()