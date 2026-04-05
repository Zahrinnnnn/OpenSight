from dataclasses import dataclass
from datetime import date

import os
import pandas as pd

from src.utils.logger import logger
from src.database.connection import get_connection


MINIMUM_BALANCE = float(os.getenv("MINIMUM_BALANCE", 0))
ALERT_THRESHOLD = float(os.getenv("ALERT_THRESHOLD", 5000))


@dataclass
class Shortfall:
    shortfall_date: date
    projected_balance: float
    days_until: int


def calculate_cash_position(forecast: pd.DataFrame, opening_balance: float) -> pd.DataFrame:
    """
    Add cumulative cash position columns to the forecast dataframe.

    cash_position — base case (yhat cumulative from opening balance)
    worst_case    — lower confidence bound cumulative
    best_case     — upper confidence bound cumulative
    """
    fc = forecast.copy()
    fc = fc.sort_values("ds").reset_index(drop=True)

    fc["cash_position"] = opening_balance + fc["yhat"].cumsum()
    fc["worst_case"]    = opening_balance + fc["yhat_lower"].cumsum()
    fc["best_case"]     = opening_balance + fc["yhat_upper"].cumsum()

    return fc


def detect_shortfalls(
    forecast: pd.DataFrame,
    minimum_balance: float = MINIMUM_BALANCE,
    alert_threshold: float = ALERT_THRESHOLD,
) -> list[Shortfall]:
    """
    Find all future dates where the projected cash position drops below
    the minimum_balance or the alert_threshold.

    Only looks at the forecast portion (dates after the last historical date).
    """
    if "cash_position" not in forecast.columns:
        raise ValueError("Call calculate_cash_position() before detect_shortfalls()")

    today = pd.Timestamp.today().normalize()
    future = forecast[forecast["ds"] > today].copy()

    shortfalls = []
    for _, row in future.iterrows():
        if row["cash_position"] < minimum_balance or row["cash_position"] < alert_threshold:
            days_until = (row["ds"].date() - today.date()).days
            shortfalls.append(Shortfall(
                shortfall_date=row["ds"].date(),
                projected_balance=round(row["cash_position"], 2),
                days_until=days_until,
            ))

    if shortfalls:
        logger.warning(
            f"{len(shortfalls)} shortfall dates detected — "
            f"first on {shortfalls[0].shortfall_date} "
            f"(balance: RM {shortfalls[0].projected_balance:,.2f})"
        )
    else:
        logger.info("No shortfalls detected in forecast horizon")

    return shortfalls


def get_forecast_summary(forecast: pd.DataFrame, opening_balance: float) -> dict:
    """
    Pull the 30/60/90-day projected net flows and closing balances.
    Returns a dict used when storing the forecast run and building the narrative.
    """
    today = pd.Timestamp.today().normalize()
    future = forecast[forecast["ds"] > today].copy()

    def net_at(days: int) -> float:
        window = future[future["ds"] <= today + pd.Timedelta(days=days)]
        return round(window["yhat"].sum(), 2)

    def balance_at(days: int) -> float:
        window = future[future["ds"] <= today + pd.Timedelta(days=days)]
        if window.empty:
            return opening_balance
        return round(opening_balance + window["yhat"].sum(), 2)

    closing = balance_at(90)

    return {
        "forecast_30": net_at(30),
        "forecast_60": net_at(60),
        "forecast_90": net_at(90),
        "closing_balance": closing,
    }


def save_shortfall_alerts(shortfalls: list[Shortfall], forecast_run_id: int) -> None:
    conn = get_connection()
    cursor = conn.cursor()

    # Clear previous alerts for this run
    cursor.execute(
        "DELETE FROM shortfall_alerts WHERE forecast_run_id = ?",
        (forecast_run_id,),
    )

    for s in shortfalls:
        cursor.execute(
            """
            INSERT INTO shortfall_alerts
                (forecast_run_id, shortfall_date, projected_balance, days_until)
            VALUES (?, ?, ?, ?)
            """,
            (forecast_run_id, str(s.shortfall_date), s.projected_balance, s.days_until),
        )

    conn.commit()
    conn.close()
    logger.info(f"Saved {len(shortfalls)} shortfall alerts for run {forecast_run_id}")
