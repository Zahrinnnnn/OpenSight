import sqlite3
import os
from pathlib import Path

from src.utils.logger import logger


def get_db_path() -> str:
    return os.getenv("DB_PATH", "data/database.db")


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # lets you access columns by name
    conn.execute("PRAGMA journal_mode=WAL")  # better concurrency
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    logger.info("Initialising database schema")
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            DATE NOT NULL,
            description     TEXT NOT NULL,
            amount          REAL NOT NULL,
            type            TEXT NOT NULL,
            category        TEXT,
            account         TEXT,
            is_recurring    INTEGER DEFAULT 0,
            is_anomaly      INTEGER DEFAULT 0,
            source_file     TEXT,
            imported_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS forecast_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date        DATETIME DEFAULT CURRENT_TIMESTAMP,
            data_from       DATE,
            data_to         DATE,
            opening_balance REAL,
            horizon_days    INTEGER,
            forecast_30     REAL,
            forecast_60     REAL,
            forecast_90     REAL,
            closing_balance REAL,
            shortfall_risk  TEXT,
            shortfall_date  DATE,
            narrative       TEXT,
            model_path      TEXT
        );

        CREATE TABLE IF NOT EXISTS recurring_payments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            description     TEXT,
            category        TEXT,
            average_amount  REAL,
            frequency       TEXT,
            last_occurrence DATE,
            next_expected   DATE,
            confidence      REAL,
            is_inflow       INTEGER,
            detected_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS anomalies (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id  INTEGER REFERENCES transactions(id),
            anomaly_type    TEXT,
            severity        TEXT,
            description     TEXT,
            detected_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS shortfall_alerts (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            forecast_run_id   INTEGER REFERENCES forecast_runs(id),
            shortfall_date    DATE,
            projected_balance REAL,
            days_until        INTEGER,
            alert_sent        INTEGER DEFAULT 0,
            alert_sent_at     DATETIME,
            resolved          INTEGER DEFAULT 0
        );
    """)

    conn.commit()
    conn.close()
    logger.success("Database schema ready")
