import pandas as pd

from src.utils.logger import logger


def aggregate_daily(df: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse transactions into daily net cash flow.
    Returns a Prophet-compatible dataframe with columns: ds, y.

    ds — date
    y  — net cash flow (inflows minus outflows) for that day
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    # Compute signed amount: positive for inflow, negative for outflow
    df["signed"] = df.apply(
        lambda r: r["amount"] if r["type"] == "inflow" else -r["amount"],
        axis=1,
    )

    daily = df.groupby("date")["signed"].sum().reset_index()
    daily.columns = ["ds", "y"]

    # Fill gaps — days with no transactions get a net flow of 0
    if len(daily) > 1:
        full_range = pd.date_range(daily["ds"].min(), daily["ds"].max(), freq="D")
        daily = daily.set_index("ds").reindex(full_range, fill_value=0).reset_index()
        daily.columns = ["ds", "y"]

    daily = daily.sort_values("ds").reset_index(drop=True)

    logger.info(
        f"Aggregated to {len(daily)} daily rows "
        f"({daily['ds'].min().date()} → {daily['ds'].max().date()})"
    )
    return daily


def get_monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns month-level inflow, outflow, and net totals.
    Useful for the dashboard overview page.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M")

    inflows  = df[df["type"] == "inflow"].groupby("month")["amount"].sum().rename("inflow")
    outflows = df[df["type"] == "outflow"].groupby("month")["amount"].sum().rename("outflow")

    summary = pd.concat([inflows, outflows], axis=1).fillna(0)
    summary["net"] = summary["inflow"] - summary["outflow"]
    summary = summary.reset_index()
    summary["month"] = summary["month"].astype(str)

    return summary
