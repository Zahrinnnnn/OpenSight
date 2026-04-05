import os
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.database.connection import init_db
from src.database.queries import get_all_transactions
from src.processing.aggregator import get_monthly_summary

init_db()

st.title("Inflow / Outflow")
st.divider()

tx_df = get_all_transactions()
if tx_df.empty:
    st.info("No transactions found. Go to **Home** and run the pipeline first.")
    st.stop()

tx_df["date"] = pd.to_datetime(tx_df["date"])

# ── Filters ───────────────────────────────────────────────────────────────────
min_date = tx_df["date"].min().date()
max_date = tx_df["date"].max().date()

f1, f2 = st.columns(2)
with f1:
    date_range = st.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
with f2:
    flow_type = st.selectbox("Transaction type", ["Both", "Inflow", "Outflow"])

if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start, end = date_range
    tx_df = tx_df[(tx_df["date"].dt.date >= start) & (tx_df["date"].dt.date <= end)]

if flow_type == "Inflow":
    tx_df = tx_df[tx_df["type"] == "inflow"]
elif flow_type == "Outflow":
    tx_df = tx_df[tx_df["type"] == "outflow"]

st.divider()

# ── Top-level KPIs ────────────────────────────────────────────────────────────
total_in  = tx_df[tx_df["type"] == "inflow"]["amount"].sum()
total_out = tx_df[tx_df["type"] == "outflow"]["amount"].sum()
net       = total_in - total_out

k1, k2, k3 = st.columns(3)
k1.metric("Total Inflow",  f"RM {total_in:,.2f}")
k2.metric("Total Outflow", f"RM {total_out:,.2f}")
k3.metric("Net Cash Flow", f"RM {net:,.2f}", delta=f"RM {net:,.2f}")

st.divider()

# ── Month-over-month trend ────────────────────────────────────────────────────
st.subheader("Month-over-Month Trend")

monthly = get_monthly_summary(tx_df)

fig_mom = go.Figure()
fig_mom.add_trace(go.Bar(
    x=monthly["month"], y=monthly["inflow"],
    name="Inflow", marker_color="#2ecc71",
))
fig_mom.add_trace(go.Bar(
    x=monthly["month"], y=monthly["outflow"],
    name="Outflow", marker_color="#e74c3c",
))
fig_mom.add_trace(go.Scatter(
    x=monthly["month"], y=monthly["net"],
    name="Net", mode="lines+markers",
    line=dict(color="#3498db", width=2),
    marker=dict(size=6),
))
fig_mom.update_layout(
    barmode="group",
    height=380,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    xaxis_title="Month",
    yaxis_title="Amount (RM)",
    margin=dict(l=0, r=0, t=10, b=0),
    plot_bgcolor="white",
    paper_bgcolor="white",
)
st.plotly_chart(fig_mom, use_container_width=True)

st.divider()

# ── Category breakdowns ───────────────────────────────────────────────────────
st.subheader("Category Breakdown")

col_in, col_out = st.columns(2)

with col_in:
    st.markdown("**Inflows by Category**")
    inflow_cats = (
        tx_df[tx_df["type"] == "inflow"]
        .groupby("category")["amount"]
        .sum()
        .reset_index()
        .sort_values("amount", ascending=False)
    )
    if not inflow_cats.empty:
        fig_in = px.pie(
            inflow_cats, values="amount", names="category",
            color_discrete_sequence=px.colors.sequential.Greens_r,
        )
        fig_in.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_in, use_container_width=True)
    else:
        st.info("No inflow data.")

with col_out:
    st.markdown("**Outflows by Category**")
    outflow_cats = (
        tx_df[tx_df["type"] == "outflow"]
        .groupby("category")["amount"]
        .sum()
        .reset_index()
        .sort_values("amount", ascending=False)
    )
    if not outflow_cats.empty:
        fig_out = px.pie(
            outflow_cats, values="amount", names="category",
            color_discrete_sequence=px.colors.sequential.Reds_r,
        )
        fig_out.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_out, use_container_width=True)
    else:
        st.info("No outflow data.")

st.divider()

# ── Category detail table ─────────────────────────────────────────────────────
st.subheader("Category Totals")

cat_summary = (
    tx_df.groupby(["category", "type"])["amount"]
    .sum()
    .unstack(fill_value=0)
    .reset_index()
)
cat_summary.columns.name = None

# Ensure both columns exist
for col in ["inflow", "outflow"]:
    if col not in cat_summary.columns:
        cat_summary[col] = 0.0

cat_summary["net"] = cat_summary["inflow"] - cat_summary["outflow"]
cat_summary = cat_summary.sort_values("outflow", ascending=False)

display = cat_summary.copy()
for col in ["inflow", "outflow", "net"]:
    display[col] = display[col].map(lambda x: f"RM {x:,.2f}")
display.columns = [c.title() for c in display.columns]
st.dataframe(display, use_container_width=True, hide_index=True)
