from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from src.utils.logger import logger
from src.utils.holidays import is_public_holiday
from src.database.connection import get_connection


HIGH_VALUE_THRESHOLD = 5000.0   # RM — for NEW_COUNTERPARTY check
GAP_DAYS = 7                    # consecutive days with no activity = GAP anomaly
SPIKE_MULTIPLIER = 2.0          # single-day outflow > 200% of 30-day average


@dataclass
class Anomaly:
    transaction_id: int | None   # None for GAP anomalies (no linked transaction)
    anomaly_type: str            # LARGE_AMOUNT | UNUSUAL_TIMING | NEW_COUNTERPARTY | SPIKE | GAP
    severity: str                # LOW | MEDIUM | HIGH
    description: str


def _severity_from_zscore(z: float) -> str:
    if z >= 5:
        return "HIGH"
    if z >= 4:
        return "MEDIUM"
    return "LOW"


def detect_large_amounts(df: pd.DataFrame) -> list[Anomaly]:
    """Flag transactions where amount > 3 std deviations from category mean."""
    anomalies = []

    for category, group in df.groupby("category"):
        if len(group) < 4:
            continue
        mean = group["amount"].mean()
        std = group["amount"].std()
        if std == 0:
            continue

        for _, row in group.iterrows():
            z = (row["amount"] - mean) / std
            if z > 3:
                anomalies.append(Anomaly(
                    transaction_id=int(row["id"]) if "id" in row else None,
                    anomaly_type="LARGE_AMOUNT",
                    severity=_severity_from_zscore(z),
                    description=(
                        f"RM {row['amount']:,.2f} in {category} is "
                        f"{z:.1f}x above category average (RM {mean:,.2f})"
                    ),
                ))

    return anomalies


def detect_unusual_timing(df: pd.DataFrame) -> list[Anomaly]:
    """Flag transactions on weekends or Malaysian public holidays."""
    anomalies = []

    for _, row in df.iterrows():
        tx_date = pd.to_datetime(row["date"]).date()
        is_weekend = tx_date.weekday() >= 5
        is_holiday = is_public_holiday(tx_date)

        if is_weekend or is_holiday:
            reason = "public holiday" if is_holiday else "weekend"
            anomalies.append(Anomaly(
                transaction_id=int(row["id"]) if "id" in row else None,
                anomaly_type="UNUSUAL_TIMING",
                severity="LOW",
                description=(
                    f"RM {row['amount']:,.2f} transaction on {tx_date} ({reason}): "
                    f"{row['description']}"
                ),
            ))

    return anomalies


def detect_new_counterparties(df: pd.DataFrame) -> list[Anomaly]:
    """
    Flag first-time vendors/counterparties with amounts above RM5,000.
    A counterparty is 'first-time' if their description only appears once in the data.
    """
    anomalies = []
    desc_counts = df["description"].value_counts()
    first_timers = desc_counts[desc_counts == 1].index

    for _, row in df.iterrows():
        if row["description"] in first_timers and row["amount"] >= HIGH_VALUE_THRESHOLD:
            anomalies.append(Anomaly(
                transaction_id=int(row["id"]) if "id" in row else None,
                anomaly_type="NEW_COUNTERPARTY",
                severity="MEDIUM",
                description=(
                    f"First-time counterparty with high value: "
                    f"'{row['description']}' — RM {row['amount']:,.2f}"
                ),
            ))

    return anomalies


def detect_daily_spikes(df: pd.DataFrame) -> list[Anomaly]:
    """Flag single days where total outflow > 200% of the 30-day rolling average."""
    anomalies = []

    outflows = df[df["type"] == "outflow"].copy()
    if outflows.empty:
        return anomalies

    outflows["date"] = pd.to_datetime(outflows["date"])
    daily = outflows.groupby("date")["amount"].sum().reset_index()
    daily = daily.sort_values("date")

    # Rolling 30-day average (excluding the current day)
    daily["rolling_avg"] = daily["amount"].shift(1).rolling(window=30, min_periods=5).mean()
    daily = daily.dropna(subset=["rolling_avg"])

    for _, row in daily.iterrows():
        if row["amount"] > SPIKE_MULTIPLIER * row["rolling_avg"]:
            # Find one representative transaction for that day
            day_txs = outflows[outflows["date"] == row["date"]]
            tx_id = int(day_txs.iloc[0]["id"]) if "id" in day_txs.columns else None
            anomalies.append(Anomaly(
                transaction_id=tx_id,
                anomaly_type="SPIKE",
                severity="HIGH",
                description=(
                    f"Daily outflow RM {row['amount']:,.2f} on {row['date'].date()} "
                    f"is {row['amount'] / row['rolling_avg']:.1f}x the 30-day average "
                    f"(RM {row['rolling_avg']:,.2f})"
                ),
            ))

    return anomalies


def detect_gaps(df: pd.DataFrame) -> list[Anomaly]:
    """Flag stretches of 7+ consecutive days with no transactions at all."""
    anomalies = []

    if df.empty:
        return anomalies

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    active_dates = sorted(df["date"].dt.date.unique())

    for i in range(len(active_dates) - 1):
        gap = (active_dates[i + 1] - active_dates[i]).days
        if gap >= GAP_DAYS:
            anomalies.append(Anomaly(
                transaction_id=None,
                anomaly_type="GAP",
                severity="LOW",
                description=(
                    f"No transactions for {gap} days: "
                    f"{active_dates[i]} to {active_dates[i + 1]}"
                ),
            ))

    return anomalies


def detect_anomalies(df: pd.DataFrame) -> list[Anomaly]:
    """Run all anomaly detectors and return the combined list."""
    all_anomalies = []
    all_anomalies.extend(detect_large_amounts(df))
    all_anomalies.extend(detect_unusual_timing(df))
    all_anomalies.extend(detect_new_counterparties(df))
    all_anomalies.extend(detect_daily_spikes(df))
    all_anomalies.extend(detect_gaps(df))

    counts = {
        "LARGE_AMOUNT":     sum(1 for a in all_anomalies if a.anomaly_type == "LARGE_AMOUNT"),
        "UNUSUAL_TIMING":   sum(1 for a in all_anomalies if a.anomaly_type == "UNUSUAL_TIMING"),
        "NEW_COUNTERPARTY": sum(1 for a in all_anomalies if a.anomaly_type == "NEW_COUNTERPARTY"),
        "SPIKE":            sum(1 for a in all_anomalies if a.anomaly_type == "SPIKE"),
        "GAP":              sum(1 for a in all_anomalies if a.anomaly_type == "GAP"),
    }
    logger.info(f"Anomaly detection complete — {len(all_anomalies)} flagged: {counts}")
    return all_anomalies


def save_anomalies(anomalies: list[Anomaly], df: pd.DataFrame) -> None:
    """
    Save anomalies to the database.
    Also marks the is_anomaly flag on the linked transaction row.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM anomalies")

    for a in anomalies:
        cursor.execute(
            """
            INSERT INTO anomalies (transaction_id, anomaly_type, severity, description)
            VALUES (?, ?, ?, ?)
            """,
            (a.transaction_id, a.anomaly_type, a.severity, a.description),
        )
        if a.transaction_id is not None:
            cursor.execute(
                "UPDATE transactions SET is_anomaly = 1 WHERE id = ?",
                (a.transaction_id,),
            )

    conn.commit()
    conn.close()
    logger.success(f"Saved {len(anomalies)} anomaly records")
