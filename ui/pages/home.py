import os
import sys
import tempfile

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.database.connection import init_db, get_connection
from src.utils.validators import load_and_validate_csv, ValidationError
from src.processing.cleaner import clean_transactions, flag_suspicious_rows
from src.processing.categoriser import categorise_transactions
from src.processing.aggregator import aggregate_daily
from src.analysis.recurring import detect_recurring_payments, save_recurring_payments
from src.analysis.anomaly import detect_anomalies, save_anomalies
from src.analysis.seasonality import get_seasonality_summary
from src.forecasting.prophet_model import train_forecast_model, generate_forecast, save_model
from src.forecasting.shortfall import (
    calculate_cash_position,
    detect_shortfalls,
    get_forecast_summary,
    save_shortfall_alerts,
)
from src.explanation.deepseek import generate_forecast_narrative, generate_shortfall_alert
from src.database.queries import save_forecast_run, get_recurring_payments, get_anomalies


def store_transactions(df, source_file: str) -> tuple[int, int]:
    conn = get_connection()
    cursor = conn.cursor()
    inserted = 0
    skipped = 0
    for _, row in df.iterrows():
        cursor.execute(
            "SELECT id FROM transactions WHERE date=? AND description=? AND amount=? AND type=?",
            (str(row["date"].date()), row["description"], row["amount"], row["type"]),
        )
        if cursor.fetchone():
            skipped += 1
            continue
        cursor.execute(
            "INSERT INTO transactions (date, description, amount, type, category, account, source_file) "
            "VALUES (?,?,?,?,?,?,?)",
            (str(row["date"].date()), row["description"], row["amount"], row["type"],
             row.get("category"), row.get("account"), source_file),
        )
        inserted += 1
    conn.commit()
    conn.close()
    return inserted, skipped


# ── Page ─────────────────────────────────────────────────────────────────────

st.title("OpenSight")
st.markdown("#### Cash Flow Forecasting Engine")
st.divider()

init_db()

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Upload Transaction Data")
    uploaded = st.file_uploader(
        "Upload your CSV file",
        type=["csv"],
        help="Required columns: date, description, amount, type  |  Optional: category, account",
    )

with col2:
    st.subheader("Settings")
    opening_balance = st.number_input(
        "Opening Balance (RM)",
        min_value=0.0,
        value=0.0,
        step=1000.0,
        format="%.2f",
        help="Your current cash balance at the time of upload",
    )
    use_deepseek = st.toggle("Use DeepSeek for categorisation", value=True)
    horizon = st.selectbox("Forecast horizon", [30, 60, 90], index=2)

st.divider()

if uploaded is not None:
    # Save to temp file so validators can read it
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write(uploaded.getbuffer())
        tmp_path = tmp.name

    st.info(f"File loaded: **{uploaded.name}** ({uploaded.size:,} bytes)")

    run_btn = st.button("▶  Run Full Pipeline", type="primary", use_container_width=True)

    if run_btn:
        progress = st.progress(0, text="Starting...")

        try:
            # 1. Validate
            progress.progress(5, text="Validating CSV...")
            df, warnings = load_and_validate_csv(tmp_path)
            if warnings:
                for w in warnings:
                    st.warning(w)

            # 2. Clean
            progress.progress(15, text="Cleaning transactions...")
            clean_df = clean_transactions(df)
            clean_df = flag_suspicious_rows(clean_df)

            # 3. Categorise
            progress.progress(25, text="Categorising transactions...")
            clean_df = categorise_transactions(clean_df, use_deepseek=use_deepseek)

            # 4. Store
            progress.progress(35, text="Storing in database...")
            inserted, skipped = store_transactions(clean_df, source_file=uploaded.name)

            # 5. Load stored rows (with IDs)
            conn = get_connection()
            stored_df = pd.read_sql_query("SELECT * FROM transactions", conn)
            conn.close()

            # 6. Recurring detection
            progress.progress(45, text="Detecting recurring payments...")
            recurring = detect_recurring_payments(stored_df)
            save_recurring_payments(recurring)
            if recurring:
                conn = get_connection()
                cursor = conn.cursor()
                for p in recurring:
                    cursor.execute(
                        "UPDATE transactions SET is_recurring=1 WHERE description LIKE ?",
                        (f"%{p.description[:20]}%",),
                    )
                conn.commit()
                conn.close()

            # 7. Anomaly detection
            progress.progress(55, text="Running anomaly detection...")
            anomalies = detect_anomalies(stored_df)
            save_anomalies(anomalies, stored_df)

            # 8. Seasonality
            progress.progress(62, text="Analysing seasonality...")
            get_seasonality_summary(stored_df)

            # 9. Build daily aggregate
            progress.progress(68, text="Aggregating daily cash flow...")
            daily_df = aggregate_daily(stored_df)

            # 10. Train Prophet
            progress.progress(75, text="Training Prophet model...")
            model = train_forecast_model(daily_df)

            # 11. Forecast
            progress.progress(83, text=f"Generating {horizon}-day forecast...")
            forecast_df = generate_forecast(model, daily_df, horizon_days=horizon)
            forecast_df = calculate_cash_position(forecast_df, opening_balance=opening_balance)

            shortfalls = detect_shortfalls(forecast_df)
            summary = get_forecast_summary(forecast_df, opening_balance)

            shortfall_risk = "NONE"
            shortfall_date = None
            if shortfalls:
                first = shortfalls[0]
                shortfall_risk = f"IN {first.days_until} DAYS"
                shortfall_date = str(first.shortfall_date)

            # 12. Narrative
            progress.progress(90, text="Generating DeepSeek narrative...")
            stored_df["date"] = pd.to_datetime(stored_df["date"])
            cutoff = stored_df["date"].max() - pd.Timedelta(days=90)
            recent = stored_df[stored_df["date"] >= cutoff]
            months = max(1, (stored_df["date"].max() - cutoff).days / 30)
            avg_inflow  = recent[recent["type"] == "inflow"]["amount"].sum() / months
            avg_outflow = recent[recent["type"] == "outflow"]["amount"].sum() / months
            avg_net     = avg_inflow - avg_outflow

            rec_df = get_recurring_payments()
            ano_df = get_anomalies()

            from src.analysis.recurring import RecurringPayment
            from src.analysis.anomaly import Anomaly
            from datetime import date as dt_date

            rec_list = [
                RecurringPayment(
                    description=r["description"], category=r["category"],
                    average_amount=r["average_amount"], frequency=r["frequency"],
                    last_occurrence=dt_date.fromisoformat(r["last_occurrence"]),
                    next_expected=dt_date.fromisoformat(r["next_expected"]),
                    confidence=r["confidence"], is_inflow=bool(r["is_inflow"]),
                )
                for _, r in rec_df.iterrows()
            ]
            ano_list = [
                Anomaly(
                    transaction_id=r.get("transaction_id"),
                    anomaly_type=r["anomaly_type"], severity=r["severity"],
                    description=r["description"],
                )
                for _, r in ano_df.iterrows()
            ]

            narrative = generate_forecast_narrative(
                avg_inflow=avg_inflow, avg_outflow=avg_outflow, avg_net=avg_net,
                current_balance=opening_balance,
                forecast_30=summary["forecast_30"], forecast_60=summary["forecast_60"],
                forecast_90=summary["forecast_90"], closing_balance=summary["closing_balance"],
                shortfall_risk=shortfall_risk,
                recurring_list=rec_list, anomaly_list=ano_list,
            )

            # 13. Save forecast run
            progress.progress(96, text="Saving forecast run...")
            run_id = save_forecast_run(
                data_from=str(stored_df["date"].min().date()),
                data_to=str(stored_df["date"].max().date()),
                opening_balance=opening_balance,
                horizon_days=horizon,
                forecast_30=summary["forecast_30"],
                forecast_60=summary["forecast_60"],
                forecast_90=summary["forecast_90"],
                closing_balance=summary["closing_balance"],
                shortfall_risk=shortfall_risk,
                shortfall_date=shortfall_date,
                narrative=narrative,
                model_path=save_model(model, run_id=0),
            )
            model_path = save_model(model, run_id=run_id)
            conn = get_connection()
            conn.execute("UPDATE forecast_runs SET model_path=? WHERE id=?", (model_path, run_id))
            conn.commit()
            conn.close()

            if shortfalls:
                save_shortfall_alerts(shortfalls, forecast_run_id=run_id)

            progress.progress(100, text="Done!")

            st.success("Pipeline complete! Navigate using the sidebar to explore results.")

            # Quick summary
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Transactions stored", f"{inserted:,}")
            c2.metric("Recurring patterns", len(recurring))
            c3.metric("Anomalies flagged", len(anomalies))
            c4.metric("Shortfall risk", shortfall_risk)

            if skipped:
                st.info(f"{skipped:,} duplicate transactions skipped.")

        except ValidationError as e:
            st.error(f"Validation failed: {e}")
        except Exception as e:
            st.error(f"Pipeline error: {e}")
            raise
        finally:
            os.unlink(tmp_path)

else:
    st.info("Upload a CSV file to get started. A sample file is available at `tests/fixtures/sample_transactions.csv`.")

    with st.expander("Expected CSV format"):
        st.code(
            "date,description,amount,type,category,account\n"
            "2026-01-05,Client Payment - ABC Sdn Bhd,15000.00,inflow,Revenue,CIMB\n"
            "2026-01-08,Office Rental January,3500.00,outflow,Rent,CIMB\n"
            "2026-01-10,Salary Run,8200.00,outflow,Payroll,HLB",
            language="text",
        )
        st.markdown(
            "**Required:** `date`, `description`, `amount`, `type` (inflow/outflow)  \n"
            "**Optional:** `category`, `account`  \n"
            "Minimum 30 transactions · Recommended 12 months for seasonal accuracy"
        )
