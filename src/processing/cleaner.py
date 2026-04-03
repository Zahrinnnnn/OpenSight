import pandas as pd
from dateutil import parser as date_parser

from src.utils.logger import logger


# Normalise type values to inflow/outflow
TYPE_MAP = {
    "credit": "inflow",
    "debit":  "outflow",
    "inflow":  "inflow",
    "outflow": "outflow",
}


def parse_date(value: str):
    """Try to parse a date string in any common format. Returns NaT on failure."""
    try:
        return date_parser.parse(str(value), dayfirst=False)
    except Exception:
        return pd.NaT


def clean_amount(value) -> float:
    """Strip currency symbols, commas, and whitespace then convert to float."""
    cleaned = str(value).replace("RM", "").replace(",", "").replace(" ", "").strip()
    try:
        return abs(float(cleaned))  # amounts are always positive in this system
    except ValueError:
        return float("nan")


def clean_transactions(df: pd.DataFrame) -> pd.DataFrame:
    logger.info(f"Starting clean — {len(df)} rows in")

    # Work on a copy
    df = df.copy()

    # Normalise column names
    df.columns = [col.strip().lower() for col in df.columns]

    # 1. Parse dates
    df["date"] = df["date"].apply(parse_date)
    bad_dates = df["date"].isna().sum()
    if bad_dates > 0:
        logger.warning(f"Dropping {bad_dates} rows with unparseable dates")
    df = df.dropna(subset=["date"])
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()  # strip time component

    # 2. Clean amounts
    df["amount"] = df["amount"].apply(clean_amount)
    bad_amounts = df["amount"].isna().sum()
    if bad_amounts > 0:
        logger.warning(f"Dropping {bad_amounts} rows with invalid amounts")
    df = df.dropna(subset=["amount"])

    # 3. Normalise type column
    df["type"] = df["type"].astype(str).str.strip().str.lower().map(TYPE_MAP)
    bad_types = df["type"].isna().sum()
    if bad_types > 0:
        logger.warning(f"Dropping {bad_types} rows with unrecognised type values")
    df = df.dropna(subset=["type"])

    # 4. Clean description
    df["description"] = df["description"].astype(str).str.strip()
    df = df[df["description"].str.len() > 0]

    # 5. Fill optional columns if missing
    if "category" not in df.columns:
        df["category"] = None
    if "account" not in df.columns:
        df["account"] = None

    df["category"] = df["category"].where(df["category"].notna(), None)
    df["account"]  = df["account"].where(df["account"].notna(), None)

    # 6. Remove true duplicates — same date, description, amount, and type
    before = len(df)
    df = df.drop_duplicates(subset=["date", "description", "amount", "type"])
    dupes_removed = before - len(df)
    if dupes_removed > 0:
        logger.info(f"Removed {dupes_removed} duplicate rows")

    # 7. Sort by date ascending
    df = df.sort_values("date").reset_index(drop=True)

    logger.success(f"Clean complete — {len(df)} rows out")
    return df


def flag_suspicious_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds an 'is_suspicious' column for rows that look odd but aren't removed.
    These are flagged for manual review, not dropped.
    """
    df = df.copy()
    df["is_suspicious"] = False

    # Zero amount transactions
    df.loc[df["amount"] == 0, "is_suspicious"] = True

    # Unusually large single transaction — above 3 std devs from mean
    mean = df["amount"].mean()
    std  = df["amount"].std()
    df.loc[df["amount"] > mean + 3 * std, "is_suspicious"] = True

    suspicious_count = df["is_suspicious"].sum()
    if suspicious_count > 0:
        logger.warning(f"{suspicious_count} suspicious rows flagged for review")

    return df
