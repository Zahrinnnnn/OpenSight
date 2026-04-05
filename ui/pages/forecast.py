import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.database.connection import init_db, get_connection
from src.database.queries import (
    get_latest_forecast_run,
    get_all_transactions,
    get_recurring_payments,
    get_anomalies,
    get_shortfall_alerts,
)
from src.forecasting.prophet_model import load_model
from src.forecasting.shortfall import calculate_cash_position
from src.analysis.seasonality import build_month_end_regressor

init_db()

st.title("Forecast")
st.divider()

run = get_latest_forecast_run()
if not run:
    st.info("No forecast found. Go to **Home** and run the pipeline first.")
    st.stop()

# ── Controls ──────────────────────────────────────────────────────────────────
ctrl1, ctrl2 = st.columns([1, 3])
with ctrl1:
    horizon = st.selectbox("Horizon", [30, 60, 90], index=2, key="fc_horizon")
    show_mode = st.radio("Chart view", ["Daily net flow", "Cumulative cash position"], key="fc_mode")

# ── Load model and regenerate forecast ───────────────────────────────────────
model_path = run.get("model_path")

if not model_path or not os.path.exists(model_path):
    st.warning("Model file not found. Re-run the pipeline from Home to regenerate.")
    st.stop()

model = load_model(model_path)

tx_df = get_all_transactions()
if tx_df.empty:
    st.info("No transactions found.")
    st.stop()

tx_df["date"] = pd.to_datetime(tx_df["date"])

# Rebuild daily aggregate from stored transactions
from src.processing.aggregator import aggregate_daily
daily_df = aggregate_daily(tx_df)

# Generate fresh forecast at selected horizon
from src.forecasting.prophet_model import generate_forecast
forecast_df = generate_forecast(model, daily_df, horizon_days=horizon)
opening_balance = run.get("opening_balance", 0) or 0
forecast_df = calculate_cash_position(forecast_df, opening_balance=opening_balance)

# Split historical vs future
last_historical = daily_df["ds"].max()
historical = forecast_df[forecast_df["ds"] <= last_historical].copy()
future = forecast_df[forecast_df["ds"] > last_historical].copy()

# ── Load markers data ─────────────────────────────────────────────────────────
anomaly_df = get_anomalies()
recurring_df = get_recurring_payments()
shortfall_df = get_shortfall_alerts(forecast_run_id=run["id"])
alert_threshold = float(os.getenv("ALERT_THRESHOLD", 5000))
minimum_balance = float(os.getenv("MINIMUM_BALANCE", 0))

# ── Build Plotly figure ───────────────────────────────────────────────────────
fig = go.Figure()

if show_mode == "Daily net flow":
    y_hist   = "y"
    y_fc     = "yhat"
    y_lower  = "yhat_lower"
    y_upper  = "yhat_upper"
    y_label  = "Daily Net Cash Flow (RM)"
else:
    y_hist   = "cash_position"
    y_fc     = "cash_position"
    y_lower  = "worst_case"
    y_upper  = "best_case"
    y_label  = "Cumulative Cash Position (RM)"
    # merge y from daily_df into historical for the cash_position view
    historical = historical.merge(
        daily_df[["ds", "y"]], on="ds", how="left"
    )

# Confidence band (forecast only)
fig.add_trace(go.Scatter(
    x=pd.concat([future["ds"], future["ds"].iloc[::-1]]),
    y=pd.concat([future[y_upper], future[y_lower].iloc[::-1]]),
    fill="toself",
    fillcolor="rgba(70,130,180,0.15)",
    line=dict(color="rgba(255,255,255,0)"),
    name="80% Confidence band",
    hoverinfo="skip",
))

# Historical line
fig.add_trace(go.Scatter(
    x=historical["ds"],
    y=historical[y_hist if y_hist in historical.columns else "yhat"],
    mode="lines",
    name="Historical",
    line=dict(color="#1a2e4a", width=2),
))

# Forecast line
fig.add_trace(go.Scatter(
    x=future["ds"],
    y=future[y_fc],
    mode="lines",
    name="Forecast",
    line=dict(color="#4682b4", width=2, dash="dash"),
))

# Shortfall threshold line
threshold = minimum_balance if show_mode == "Cumulative cash position" else None
if threshold is not None:
    fig.add_hline(
        y=threshold,
        line=dict(color="red", width=1, dash="dot"),
        annotation_text="Min balance",
        annotation_position="bottom right",
    )

# Alert threshold line (only on cumulative view)
if show_mode == "Cumulative cash position" and alert_threshold > minimum_balance:
    fig.add_hline(
        y=alert_threshold,
        line=dict(color="orange", width=1, dash="dot"),
        annotation_text=f"Alert threshold RM {alert_threshold:,.0f}",
        annotation_position="top right",
    )

# Anomaly markers
if not anomaly_df.empty and "date" in anomaly_df.columns:
    anomaly_dates = pd.to_datetime(anomaly_df["date"].dropna())
    y_vals = [0] * len(anomaly_dates)
    fig.add_trace(go.Scatter(
        x=anomaly_dates,
        y=y_vals,
        mode="markers",
        name="Anomaly",
        marker=dict(color="orange", size=9, symbol="circle"),
        hovertext=anomaly_df["description"].fillna("").tolist(),
        hoverinfo="text+x",
    ))

# Recurring payment vertical markers (next expected dates)
if not recurring_df.empty:
    next_dates = pd.to_datetime(recurring_df["next_expected"].dropna())
    for d, desc in zip(next_dates, recurring_df["description"]):
        if d > last_historical:
            fig.add_vline(
                x=d.timestamp() * 1000,
                line=dict(color="rgba(128,0,128,0.35)", width=1, dash="dot"),
            )

fig.update_layout(
    height=520,
    xaxis=dict(
        title="Date",
        rangeslider=dict(visible=True),
        type="date",
    ),
    yaxis=dict(title=y_label),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    hovermode="x unified",
    margin=dict(l=0, r=0, t=10, b=0),
    plot_bgcolor="white",
    paper_bgcolor="white",
)

with ctrl2:
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Summary metrics ───────────────────────────────────────────────────────────
st.subheader("Forecast Summary")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Opening balance",    f"RM {opening_balance:,.0f}")
c2.metric(f"Net flow (30d)",    f"RM {run.get('forecast_30', 0):,.0f}")
c3.metric(f"Net flow (60d)",    f"RM {run.get('forecast_60', 0):,.0f}")
c4.metric(f"Net flow (90d)",    f"RM {run.get('forecast_90', 0):,.0f}")

st.divider()

# ── Shortfalls table ──────────────────────────────────────────────────────────
if not shortfall_df.empty:
    st.subheader("Projected Shortfall Dates")
    display = shortfall_df[["shortfall_date", "projected_balance", "days_until"]].copy()
    display.columns = ["Date", "Projected Balance (RM)", "Days Until"]
    display["Projected Balance (RM)"] = display["Projected Balance (RM)"].map(lambda x: f"RM {x:,.2f}")
    st.dataframe(display, use_container_width=True, hide_index=True)

# ── Recurring next dates ──────────────────────────────────────────────────────
if not recurring_df.empty:
    with st.expander("Upcoming recurring payments"):
        disp = recurring_df[["description", "average_amount", "frequency", "next_expected", "confidence"]].copy()
        disp["average_amount"] = disp["average_amount"].map(lambda x: f"RM {x:,.2f}")
        disp["confidence"]     = disp["confidence"].map(lambda x: f"{x:.0%}")
        disp.columns = ["Description", "Avg Amount", "Frequency", "Next Expected", "Confidence"]
        st.dataframe(disp, use_container_width=True, hide_index=True)
