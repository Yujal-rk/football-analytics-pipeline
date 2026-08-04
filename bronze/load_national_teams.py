import psycopg2
import csv
import io
import os
import logging


# ── LOGGING ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ── CONNECTION SETTINGS ───────────────────────────────────────────
DB_HOST     = "localhost"
DB_PORT     = 5432
DB_NAME     = "football_db"
DB_USER     = "postgres"
DB_PASSWORD = "Nepal123"


CSV_PATH = os.path.join(os.path.dirname(__file__), "source", "national_teams.csv")
# ─────────────────────────────────────────────────────────────────


# Bronze / raw landing table: mirrors the source CSV as-is.
# Only national_team_id is constrained (structural identity).
# Everything else loads as-is, including blanks — cleaning happens in Silver.
CREATE_TABLE_SQL = """
DROP TABLE IF EXISTS national_teams;


CREATE TABLE national_teams (
    national_team_id      INTEGER       PRIMARY KEY,
    name                   VARCHAR(100),
    team_code               VARCHAR(50),
    country_id                INTEGER,
    country_name               VARCHAR(100),
    country_code                 VARCHAR(10),
    confederation                  VARCHAR(50),
    team_image_url                  VARCHAR(500),
    squad_size                        INTEGER,
    average_age                         DECIMAL(5, 2),
    foreigners_number                     INTEGER,
    foreigners_percentage                   DECIMAL(5, 2),
    total_market_value                        VARCHAR(50),
    coach_name                                  VARCHAR(100),
    fifa_ranking                                  INTEGER,
    last_season                                     INTEGER,
    url                                                VARCHAR(500)
);
"""




def get_connection():
    """Open and return a database connection."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
            user=DB_USER, password=DB_PASSWORD
        )
        logger.info(f"Connected to {DB_NAME} on {DB_HOST}:{DB_PORT}")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Failed to connect to database: {e}")
        raise




def create_table(conn):
    """Drop and recreate the national_teams table."""
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
        conn.commit()
        logger.info("Table 'national_teams' created successfully")
    except psycopg2.Error as e:
        logger.error(f"Failed to create table: {e}")
        raise




def load_csv(conn, csv_path):
    """
    Load the CSV into the national_teams table using PostgreSQL's COPY command.
    Bronze layer: no filtering, no value substitution — loads the source as-is.

    Handles quoted fields containing commas by converting to tab-delimited format.
    """
    try:
        with conn.cursor() as cur:
            with open(csv_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                next(reader)  # skip header row


                cleaned = io.StringIO()
                writer = csv.writer(cleaned, delimiter='\t')  # Use tab delimiter instead of comma
                for fields in reader:
                    writer.writerow(fields)


                cleaned.seek(0)
                cur.copy_from(file=cleaned, table="national_teams", sep="\t", null="")  # Tell COPY to use tab
            row_count = cur.rowcount
        conn.commit()
        logger.info(f"Loaded {row_count:,} rows into 'national_teams'")
        return row_count


    except FileNotFoundError:
        logger.error(f"CSV file not found: {csv_path}")
        raise
    except psycopg2.Error as e:
        logger.error(f"Failed to load CSV: {e}")
        raise


def verify(conn):
    """Sanity check -- show national teams by fifa_ranking."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT name, fifa_ranking, confederation, squad_size
                FROM national_teams
                WHERE fifa_ranking > 0
                ORDER BY fifa_ranking ASC
                LIMIT 10;
            """)
            rows = cur.fetchall()


        logger.info("Top 10 national teams by FIFA ranking:")
        for name, ranking, confed, squad_size in rows:
            logger.info(f"  {name:<30} rank={ranking:>3} confed={confed:<10} squad={squad_size}")
    except psycopg2.Error as e:
        logger.error(f"Failed to run verification query: {e}")
        raise




def main():
    try:
        logger.info("Starting national_teams loader...")
        conn = get_connection()
        create_table(conn)
        logger.info(f"Loading {CSV_PATH}...")
        load_csv(conn, CSV_PATH)
        verify(conn)
        conn.close()
        logger.info("Load complete")
    except Exception as e:
        logger.error(f"Loader failed: {e}")
        raise




if __name__ == "__main__":
    main()
