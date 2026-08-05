"""quality.py -- Gold layer quality gate, run on the transformed fact
table just before load."""
import logging
import pandas as pd

logger = logging.getLogger(__name__)


class DataQualityError(Exception):
    pass


def check_row_count(df, min_rows=1):
    count = len(df)
    return {"check": "row_count", "passed": count >= min_rows,
            "detail": f"{count} rows (min {min_rows})"}


def check_no_null_required_fks(df):
    bad = int(df["player_id"].isna().sum() + df["date_id"].isna().sum())
    return {"check": "no_null_required_fks", "passed": bad == 0,
            "detail": f"{bad} rows with NULL player_id/date_id"}


def check_no_negative_stats(df):
    bad = int(((df["goals"] < 0) | (df["assists"] < 0) |
               (df["yellow_cards"] < 0) | (df["red_cards"] < 0) |
               (df["minutes_played"] < 0)).sum())
    return {"check": "no_negative_stats", "passed": bad == 0,
            "detail": f"{bad} rows with negative stats"}


def check_minutes_range(df):
    bad = int((df["minutes_played"] > 120).sum())
    return {"check": "minutes_range", "passed": bad == 0,
            "detail": f"{bad} rows with minutes_played > 120"}


def run_quality_checks(df: pd.DataFrame) -> dict:
    checks = [
        check_row_count(df),
        check_no_null_required_fks(df),
        check_no_negative_stats(df),
        check_minutes_range(df),
    ]
    failed = [c for c in checks if not c["passed"]]
    if failed:
        first = failed[0]
        raise DataQualityError(f"Quality check failed: {first['check']} — {first['detail']}")

    logger.info(f"Quality gate passed: {len(df):,} rows, {len(checks)} checks")
    for c in checks:
        logger.info(f"  [OK] {c['check']}: {c['detail']}")
    return {"passed": True, "checks": checks, "row_count": len(df)}