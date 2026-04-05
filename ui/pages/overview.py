import os
import sys

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.database.connection import init_db
from src.database.queries import get_latest_forecast_run, get_all_transactions, get_shortfall_alerts

init_db()

st.title("Overview")
st.divider()

run = get_latest_forecast_run()

if not run:
    st.info("No forecast found. Go to **Home** and run the pipeline first.")
    st.stop()

# ── Shortfall alert banner ────────────────────────────────────────────────────
shortfall_risk = run.get("shortfall_risk", "NONE")
if shortfall_risk and shortfall_risk != "NONE":
    st.error(
        f"⚠️  **Cash Shortfall Detected** — Projected balance drops below threshold "
        f"**{shortfall_risk.lower()}**. Review the Forecast page for details.",
        icon="🚨",
    )

# ── KPI cards ─────────────────────────────────────────────────────────────────
opening   = run.get("opening_balance", 0) or 0
closing   = run.get("closing_balance", 0) or 0
fc30      = run.get("forecast_30", 0) or 0
fc60      = run.get("forecast_60", 0) or 0
fc90      = run.get("forecast_90", 0) or 0

proj_30 = opening + fc30
proj_60 = opening + fc60
proj_90 = opening + fc90

col1, col2, col3, col4 = st.columns(4)
col1.metric("Current Balance",    f"RM {opening:,.0f}")
col2.metric("Balance in 30 days", f"RM {proj_30:,.0f}", delta=f"RM {fc30:,.0f}")
col3.metric("Balance in 60 days", f"RM {proj_60:,.0f}", delta=f"RM {fc60:,.0f}")
col4.metric("Balance in 90 days", f"RM {proj_90:,.0f}", delta=f"RM {fc90:,.0f}")

st.divider()

# ── Burn rate and runway ──────────────────────────────────────────────────────
tx_df = get_all_transactions()

if not tx_df.empty:
    tx_df["date"] = pd.to_datetime(tx_df["date"])
    cutoff = tx_df["date"].max() - pd.Timedelta(days=90)
    recent = tx_df[tx_df["date"] >= cutoff]
    months = max(1, (tx_df["date"].max() - cutoff).days / 30)

    avg_monthly_outflow = recent[recent["type"] == "outflow"]["amount"].sum() / months
    avg_monthly_inflow  = recent[recent["type"] == "inflow"]["amount"].sum() / months
    burn_rate = avg_monthly_outflow - avg_monthly_inflow  # net burn (positive = burning cash)
    runway = (opening / burn_rate) if burn_rate > 0 else None

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Avg Monthly Inflow",  f"RM {avg_monthly_inflow:,.0f}")
    col6.metric("Avg Monthly Outflow", f"RM {avg_monthly_outflow:,.0f}")
    col7.metric("Monthly Burn Rate",   f"RM {max(0, burn_rate):,.0f}")
    col8.metric(
        "Runway",
        f"{runway:.1f} months" if runway and runway > 0 else "Positive cash flow",
    )

st.divider()

# ── Forecast run info ─────────────────────────────────────────────────────────
col_a, col_b = st.columns(2)

with col_a:
    st.markdown("**Latest Forecast Run**")
    st.markdown(f"- Run date: `{run.get('run_date', 'N/A')}`")
    st.markdown(f"- Data range: `{run.get('data_from')}` → `{run.get('data_to')}`")
    st.markdown(f"- Horizon: `{run.get('horizon_days')} days`")
    st.markdown(f"- Shortfall risk: `{shortfall_risk}`")
    if run.get("shortfall_date"):
        st.markdown(f"- First shortfall date: `{run.get('shortfall_date')}`")

with col_b:
    # Shortfall alerts table
    alerts_df = get_shortfall_alerts(forecast_run_id=run["id"])
    if not alerts_df.empty:
        st.markdown("**Projected Shortfall Dates**")
        display = alerts_df[["shortfall_date", "projected_balance", "days_until"]].copy()
        display.columns = ["Date", "Projected Balance (RM)", "Days Until"]
        display["Projected Balance (RM)"] = display["Projected Balance (RM)"].map(
            lambda x: f"RM {x:,.2f}"
        )
        st.dataframe(display, use_container_width=True, hide_index=True)
    else:
        st.success("✅ No shortfalls projected in the forecast horizon.")

st.divider()

# ── Recent transactions ───────────────────────────────────────────────────────
if not tx_df.empty:
    st.subheader("Recent Transactions")
    recent_10 = tx_df.sort_values("date", ascending=False).head(10)
    display = recent_10[["date", "description", "amount", "type", "category"]].copy()
    display["amount"] = display["amount"].map(lambda x: f"RM {x:,.2f}")
    display.columns = ["Date", "Description", "Amount", "Type", "Category"]
    st.dataframe(display, use_container_width=True, hide_index=True)
