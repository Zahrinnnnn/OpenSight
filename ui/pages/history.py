import os
import sys

import streamlit as st
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.database.connection import init_db
from src.database.queries import get_all_forecast_runs, get_shortfall_alerts

init_db()

st.title("Forecast History")
st.divider()

runs_df = get_all_forecast_runs()

if runs_df.empty:
    st.info("No forecast runs yet. Go to **Home** and run the pipeline first.")
    st.stop()

st.markdown(f"**{len(runs_df)}** forecast run(s) on record.")

# ── Summary table ─────────────────────────────────────────────────────────────
display = runs_df[[
    "id", "run_date", "data_from", "data_to",
    "opening_balance", "closing_balance", "shortfall_risk", "horizon_days",
]].copy()

for col in ["opening_balance", "closing_balance"]:
    display[col] = display[col].map(lambda x: f"RM {x:,.0f}" if x is not None else "—")

display.columns = [
    "Run ID", "Run Date", "Data From", "Data To",
    "Opening Balance", "Closing Balance", "Shortfall Risk", "Horizon (days)",
]

st.dataframe(display, use_container_width=True, hide_index=True)

st.divider()

# ── Drill-down ────────────────────────────────────────────────────────────────
st.subheader("Drill Down")

run_ids = runs_df["id"].tolist()
selected_id = st.selectbox("Select forecast run", run_ids, format_func=lambda x: f"Run #{x}")

selected = runs_df[runs_df["id"] == selected_id].iloc[0]

col1, col2 = st.columns(2)

with col1:
    st.markdown("**Run Details**")
    st.markdown(f"- Run date: `{selected.get('run_date', 'N/A')}`")
    st.markdown(f"- Data range: `{selected.get('data_from')}` → `{selected.get('data_to')}`")
    st.markdown(f"- Horizon: `{selected.get('horizon_days')} days`")
    st.markdown(f"- Opening balance: RM `{selected.get('opening_balance', 0):,.2f}`")
    st.markdown(f"- Closing balance: RM `{selected.get('closing_balance', 0):,.2f}`")
    st.markdown(f"- Shortfall risk: `{selected.get('shortfall_risk', 'NONE')}`")

with col2:
    st.markdown("**Forecast Figures**")
    fc30 = selected.get("forecast_30", 0) or 0
    fc60 = selected.get("forecast_60", 0) or 0
    fc90 = selected.get("forecast_90", 0) or 0
    opening = selected.get("opening_balance", 0) or 0

    st.metric("30-day projected balance", f"RM {opening + fc30:,.0f}")
    st.metric("60-day projected balance", f"RM {opening + fc60:,.0f}")
    st.metric("90-day projected balance", f"RM {opening + fc90:,.0f}")

# Shortfall alerts for this run
alerts_df = get_shortfall_alerts(forecast_run_id=selected_id)
if not alerts_df.empty:
    st.divider()
    st.markdown("**Shortfall Alerts for This Run**")
    disp = alerts_df[["shortfall_date", "projected_balance", "days_until", "alert_sent"]].copy()
    disp["projected_balance"] = disp["projected_balance"].map(lambda x: f"RM {x:,.2f}")
    disp["alert_sent"] = disp["alert_sent"].map(lambda x: "Yes" if x else "No")
    disp.columns = ["Date", "Projected Balance", "Days Until", "Alert Sent"]
    st.dataframe(disp, use_container_width=True, hide_index=True)

# Narrative
narrative = selected.get("narrative", "")
if narrative:
    st.divider()
    st.markdown("**Forecast Commentary**")
    st.markdown(
        f'<div style="background:#f8f9fa;border-left:4px solid #4682b4;'
        f'padding:1rem 1.2rem;border-radius:4px;font-size:1rem;line-height:1.7;">'
        f"{narrative}</div>",
        unsafe_allow_html=True,
    )
