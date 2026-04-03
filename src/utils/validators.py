import pandas as pd
from pathlib import Path

from src.utils.logger import logger


REQUIRED_COLUMNS = {"date", "description", "amount", "type"}
VALID_TYPES = {"inflow", "outflow", "credit", "debit"}
MIN_ROWS = 30


class ValidationError(Exception):
    pass


def validate_csv_file(file_path: str) -> None:
    path = Path(file_path)

    if not path.exists():
        raise ValidationError(f"File not found: {file_path}")

    if path.suffix.lower() != ".csv":
        raise ValidationError(f"Expected a .csv file, got: {path.suffix}")

    if path.stat().st_size == 0:
        raise ValidationError("File is empty")


def validate_dataframe(df: pd.DataFrame) -> list[str]:
    """
    Validates a raw CSV dataframe. Returns a list of warning messages
    for non-fatal issues. Raises ValidationError for fatal ones.
    """
    warnings = []

    # Check required columns exist (case-insensitive)
    df.columns = [col.strip().lower() for col in df.columns]
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValidationError(f"Missing required columns: {', '.join(sorted(missing))}")

    # Check minimum row count
    if len(df) < MIN_ROWS:
        warnings.append(
            f"Only {len(df)} rows found — minimum {MIN_ROWS} needed for reliable forecasting"
        )

    # Check amount column is numeric (after stripping symbols)
    amount_clean = (
        df["amount"]
        .astype(str)
        .str.replace(r"[RM,\s]", "", regex=True)
    )
    non_numeric = amount_clean[pd.to_numeric(amount_clean, errors="coerce").isna()]
    if not non_numeric.empty:
        raise ValidationError(
            f"Non-numeric values in 'amount' column at rows: {list(non_numeric.index[:5])}"
        )

    # Check type column contains known values
    type_col = df["type"].astype(str).str.strip().str.lower()
    unknown_types = type_col[~type_col.isin(VALID_TYPES)].unique()
    if len(unknown_types) > 0:
        warnings.append(
            f"Unknown values in 'type' column: {list(unknown_types)}. Expected: inflow/outflow"
        )

    # Check date column can be parsed
    try:
        pd.to_datetime(df["date"], infer_datetime_format=True, errors="raise")
    except Exception:
        # Try a looser check — just see how many fail
        failed = pd.to_datetime(df["date"], errors="coerce").isna().sum()
        if failed > 0:
            warnings.append(f"{failed} dates could not be parsed and will be skipped")

    # Warn if data looks thin for seasonality detection
    try:
        parsed_dates = pd.to_datetime(df["date"], errors="coerce").dropna()
        date_range_days = (parsed_dates.max() - parsed_dates.min()).days
        if date_range_days < 90:
            warnings.append(
                f"Data spans only {date_range_days} days — at least 90 days recommended for forecasting"
            )
        elif date_range_days < 365:
            warnings.append(
                f"Data spans {date_range_days} days — 365 days recommended for seasonal pattern detection"
            )
    except Exception:
        pass

    for w in warnings:
        logger.warning(w)

    return warnings


def load_and_validate_csv(file_path: str) -> tuple[pd.DataFrame, list[str]]:
    validate_csv_file(file_path)
    df = pd.read_csv(file_path)
    warnings = validate_dataframe(df)
    logger.info(f"Loaded {len(df)} rows from {file_path}")
    return df, warnings
