import os
import sys

import streamlit as st
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.database.connection import init_db
from src.database.queries import get_anomalies

init_db()

st.title("Anomalies")
st.divider()

df = get_anomalies()

if df.empty:
    st.info("No anomalies detected. Go to **Home** and run the pipeline first.")
    st.stop()

# ── Summary KPIs ──────────────────────────────────────────────────────────────
high   = (df["severity"] == "HIGH").sum()
medium = (df["severity"] == "MEDIUM").sum()
low    = (df["severity"] == "LOW").sum()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total anomalies", len(df))
k2.metric("High severity",   high,   delta=None if not high else "review now")
k3.metric("Medium severity", medium)
k4.metric("Low severity",    low)

st.divider()

# ── Filters ───────────────────────────────────────────────────────────────────
f1, f2 = st.columns(2)
with f1:
    type_filter = st.multiselect(
        "Anomaly type",
        options=df["anomaly_type"].unique().tolist(),
        default=df["anomaly_type"].unique().tolist(),
    )
with f2:
    sev_filter = st.multiselect(
        "Severity",
        options=["HIGH", "MEDIUM", "LOW"],
        default=["HIGH", "MEDIUM", "LOW"],
    )

filtered = df[
    df["anomaly_type"].isin(type_filter) &
    df["severity"].isin(sev_filter)
]

# ── Table ─────────────────────────────────────────────────────────────────────
st.subheader(f"Flagged Transactions ({len(filtered)})")

SEVERITY_COLOUR = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟡"}

display = filtered[[
    "anomaly_type", "severity", "description", "date", "amount",
]].copy()

# date and amount may be None for GAP anomalies
if "date" in display.columns:
    display["date"] = display["date"].fillna("—")
if "amount" in display.columns:
    display["amount"] = display["amount"].apply(
        lambda x: f"RM {x:,.2f}" if x and str(x) != "nan" else "—"
    )

display["severity"] = display["severity"].map(
    lambda s: f"{SEVERITY_COLOUR.get(s, '')} {s}"
)

display.columns = ["Type", "Severity", "Description", "Date", "Amount"]
st.dataframe(display, use_container_width=True, hide_index=True)

st.divider()

# ── Type breakdown ────────────────────────────────────────────────────────────
st.subheader("Breakdown by Type")
type_counts = df["anomaly_type"].value_counts().reset_index()
type_counts.columns = ["Type", "Count"]

import plotly.express as px
fig = px.bar(
    type_counts, x="Type", y="Count",
    color="Type",
    color_discrete_sequence=px.colors.qualitative.Set2,
)
fig.update_layout(
    height=300, showlegend=False,
    margin=dict(l=0, r=0, t=10, b=0),
    plot_bgcolor="white", paper_bgcolor="white",
)
st.plotly_chart(fig, use_container_width=True)
