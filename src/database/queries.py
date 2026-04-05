import pandas as pd

from src.database.connection import get_connection


def save_forecast_run(
    data_from: str,
    data_to: str,
    opening_balance: float,
    horizon_days: int,
    forecast_30: float,
    forecast_60: float,
    forecast_90: float,
    closing_balance: float,
    shortfall_risk: str,
    shortfall_date: str | None,
    narrative: str,
    model_path: str,
) -> int:
    """Insert a forecast run record and return the new row ID."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO forecast_runs (
            data_from, data_to, opening_balance, horizon_days,
            forecast_30, forecast_60, forecast_90, closing_balance,
            shortfall_risk, shortfall_date, narrative, model_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data_from, data_to, opening_balance, horizon_days,
            forecast_30, forecast_60, forecast_90, closing_balance,
            shortfall_risk, shortfall_date, narrative, model_path,
        ),
    )

    run_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return run_id


def get_latest_forecast_run() -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM forecast_runs ORDER BY run_date DESC LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_forecast_runs() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM forecast_runs ORDER BY run_date DESC", conn
    )
    conn.close()
    return df


def get_all_transactions() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM transactions ORDER BY date ASC", conn
    )
    conn.close()
    return df


def get_recurring_payments() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM recurring_payments ORDER BY next_expected ASC", conn
    )
    conn.close()
    return df


def get_anomalies() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT a.*, t.date, t.description as tx_description, t.amount, t.category
        FROM anomalies a
        LEFT JOIN transactions t ON a.transaction_id = t.id
        ORDER BY a.detected_at DESC
        """,
        conn,
    )
    conn.close()
    return df


def get_shortfall_alerts(forecast_run_id: int | None = None) -> pd.DataFrame:
    conn = get_connection()
    if forecast_run_id is not None:
        df = pd.read_sql_query(
            "SELECT * FROM shortfall_alerts WHERE forecast_run_id = ? ORDER BY shortfall_date ASC",
            conn,
            params=(forecast_run_id,),
        )
    else:
        df = pd.read_sql_query(
            "SELECT * FROM shortfall_alerts ORDER BY shortfall_date ASC", conn
        )
    conn.close()
    return df
