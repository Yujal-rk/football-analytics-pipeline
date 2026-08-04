"""
quality.py -- Silver layer quality gate.
...
This module documents the concrete quality issues found and investigated
during development (see docs/decisions_log.md for the full story of how
each one was discovered):
  1. appearances.minutes_played > 120  -> 3 known bad rows, filtered.
  2. appearances.player_name blank      -> allowed (name dropped in Silver
                                             anyway, so this is moot there).
  3. competitions.country_id = -1       -> sentinel value, converted to NULL.
  4. clubs / players money fields formatted as strings, not numerics
     (validated by type, not filtered).
  5. clubs.domestic_competition_id referencing a competition_id not
     present in bronze.competitions -> orphan clubs, excluded from Silver.
  6. players.current_club_id referencing a club_id not present in
     bronze.clubs -> orphan players, excluded from Silver.
  7. games.competition_id referencing a competition_id not present in
     bronze.competitions -> orphan games, excluded from Silver.
"""
import logging

logger = logging.getLogger(__name__)


class DataQualityError(Exception):
    """Raised when a quality check fails badly enough to halt the pipeline."""
    pass


def check_row_count(cur, table, min_rows=1):
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    count = cur.fetchone()[0]
    if count < min_rows:
        raise DataQualityError(f"{table}: only {count} rows (min {min_rows})")
    logger.info(f"  [OK] {table}: {count:,} rows")
    return count


def check_no_orphan_appearances(cur):
    """appearances.game_id / player_id must exist in games / players."""
    cur.execute("""
        SELECT COUNT(*) FROM bronze.appearances a
        WHERE a.game_id IS NULL
           OR a.player_id IS NULL
           OR NOT EXISTS (SELECT 1 FROM bronze.games g WHERE g.game_id = a.game_id)
           OR NOT EXISTS (SELECT 1 FROM bronze.players p WHERE p.player_id = a.player_id)
    """)
    orphans = cur.fetchone()[0]
    logger.info(f"  [INFO] appearances with missing/orphan game_id or player_id: {orphans:,} (excluded from Silver)")
    return orphans


def check_minutes_played_range(cur):
    cur.execute("""
        SELECT COUNT(*) FROM bronze.appearances
        WHERE minutes_played > 120 OR minutes_played < 0
    """)
    bad = cur.fetchone()[0]
    logger.warning(f"  [WARN] appearances with minutes_played outside 0-120: {bad} (excluded from Silver)")
    return bad


def check_orphan_clubs(cur):
    """clubs.domestic_competition_id must exist in bronze.competitions (or be blank/null)."""
    cur.execute("""
        SELECT COUNT(*) FROM bronze.clubs c
        WHERE c.domestic_competition_id IS NOT NULL
          AND c.domestic_competition_id != ''
          AND NOT EXISTS (
              SELECT 1 FROM bronze.competitions comp
              WHERE comp.competition_id = c.domestic_competition_id
          )
    """)
    orphans = cur.fetchone()[0]
    logger.warning(f"  [WARN] clubs with domestic_competition_id not in competitions: {orphans:,} (excluded from Silver)")
    return orphans


def check_orphan_players(cur):
    """players.current_club_id must exist in bronze.clubs (or be null)."""
    cur.execute("""
        SELECT COUNT(*) FROM bronze.players p
        WHERE p.current_club_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM bronze.clubs c WHERE c.club_id = p.current_club_id
          )
    """)
    orphans = cur.fetchone()[0]
    logger.warning(f"  [WARN] players with current_club_id not in clubs: {orphans:,} (excluded from Silver)")
    return orphans


def check_orphan_games(cur):
    """games.competition_id must exist in bronze.competitions (or be blank/null)."""
    cur.execute("""
        SELECT COUNT(*) FROM bronze.games g
        WHERE g.competition_id IS NOT NULL
          AND g.competition_id != ''
          AND NOT EXISTS (
              SELECT 1 FROM bronze.competitions comp
              WHERE comp.competition_id = g.competition_id
          )
    """)
    orphans = cur.fetchone()[0]
    logger.warning(f"  [WARN] games with competition_id not in competitions: {orphans:,} (excluded from Silver)")
    return orphans


def run_quality_checks(conn):
    """
    Run all Bronze -> Silver quality checks. Returns a summary dict.
    Raises DataQualityError only for checks severe enough to block the run
    (currently: empty source tables).
    """
    logger.info("Running Silver quality gate...")
    with conn.cursor() as cur:
        for table in ("bronze.competitions", "bronze.clubs", "bronze.players",
                      "bronze.games", "bronze.appearances"):
            check_row_count(cur, table)

        orphan_appearances = check_no_orphan_appearances(cur)
        bad_minutes_count = check_minutes_played_range(cur)
        orphan_clubs = check_orphan_clubs(cur)
        orphan_players = check_orphan_players(cur)
        orphan_games = check_orphan_games(cur)

    logger.info("Quality gate passed (with documented exclusions logged above).")
    return {
        "orphan_appearances": orphan_appearances,
        "bad_minutes_played": bad_minutes_count,
        "orphan_clubs": orphan_clubs,
        "orphan_players": orphan_players,
        "orphan_games": orphan_games,
    }