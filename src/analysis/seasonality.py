import pandas as pd

from src.utils.logger import logger


# Categories that typically spike at month-end
MONTH_END_CATEGORIES = {"Payroll", "Rent", "Utilities", "Loan Repayment", "Insurance"}

# Last N days of the month count as "month-end"
MONTH_END_WINDOW = 5

# Last N days of March, June, September, December count as "quarter-end"
QUARTER_END_MONTHS = {3, 6, 9, 12}
QUARTER_END_WINDOW = 7


def _is_month_end(d: pd.Timestamp) -> bool:
    return d.day >= (d.days_in_month - MONTH_END_WINDOW + 1)


def _is_quarter_end(d: pd.Timestamp) -> bool:
    return d.month in QUARTER_END_MONTHS and _is_month_end(d)


def detect_month_end_spikes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Find categories with significantly higher activity in the last 5 days of the month.
    Returns a summary dataframe showing which categories spike at month-end.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["is_month_end"] = df["date"].apply(_is_month_end)

    results = []
    for category in MONTH_END_CATEGORIES:
        cat_df = df[df["category"] == category]
        if cat_df.empty:
            continue

        month_end_total = cat_df[cat_df["is_month_end"]]["amount"].sum()
        other_total = cat_df[~cat_df["is_month_end"]]["amount"].sum()

        if other_total == 0:
            continue

        ratio = month_end_total / (month_end_total + other_total)
        results.append({
            "category": category,
            "month_end_amount": round(month_end_total, 2),
            "other_amount": round(other_total, 2),
            "month_end_ratio": round(ratio, 3),
            "has_spike": ratio > 0.40,  # more than 40% of activity in last 5 days
        })

    return pd.DataFrame(results)


def detect_quarter_end_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect elevated outflow activity in the last week of each quarter.
    Useful for flagging tax payments, audit fees, and big vendor settlements.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["is_quarter_end"] = df["date"].apply(_is_quarter_end)

    outflows = df[df["type"] == "outflow"]
    if outflows.empty:
        return pd.DataFrame()

    quarter_end_avg = (
        outflows[outflows["is_quarter_end"]].groupby("category")["amount"].mean()
    )
    overall_avg = outflows.groupby("category")["amount"].mean()

    comparison = pd.DataFrame({
        "quarter_end_avg": quarter_end_avg,
        "overall_avg": overall_avg,
    }).dropna()

    comparison["ratio"] = comparison["quarter_end_avg"] / comparison["overall_avg"]
    comparison["elevated"] = comparison["ratio"] > 1.5
    comparison = comparison.reset_index().rename(columns={"index": "category"})

    return comparison


def build_month_end_regressor(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a month_end binary regressor column to a daily Prophet dataframe.
    This is passed to Prophet as an additional regressor in Phase 4.
    """
    daily_df = daily_df.copy()
    daily_df["ds"] = pd.to_datetime(daily_df["ds"])
    daily_df["month_end"] = daily_df["ds"].apply(_is_month_end).astype(int)
    return daily_df


def get_seasonality_summary(df: pd.DataFrame) -> dict:
    """
    Run all seasonality checks and return a summary dict.
    Used to inform the DeepSeek narrative in Phase 4.
    """
    month_end_spikes = detect_month_end_spikes(df)
    quarter_end = detect_quarter_end_patterns(df)

    spiking_categories = (
        month_end_spikes[month_end_spikes["has_spike"]]["category"].tolist()
        if not month_end_spikes.empty else []
    )
    elevated_quarter_categories = (
        quarter_end[quarter_end["elevated"]]["category"].tolist()
        if not quarter_end.empty else []
    )

    summary = {
        "month_end_spike_categories": spiking_categories,
        "quarter_end_elevated_categories": elevated_quarter_categories,
        "month_end_detail": month_end_spikes.to_dict(orient="records"),
        "quarter_end_detail": quarter_end.to_dict(orient="records"),
    }

    logger.info(
        f"Seasonality — month-end spikes in: {spiking_categories}, "
        f"quarter-end elevated in: {elevated_quarter_categories}"
    )
    return summary
