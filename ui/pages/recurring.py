import os
import sys

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.database.connection import init_db
from src.database.queries import get_recurring_payments

init_db()

st.title("Recurring Payments")
st.divider()

df = get_recurring_payments()

if df.empty:
    st.info("No recurring payments detected. Go to **Home** and run the pipeline first.")
    st.stop()

# ── Summary KPIs ──────────────────────────────────────────────────────────────
inflows  = df[df["is_inflow"] == 1]
outflows = df[df["is_inflow"] == 0]

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total patterns",     len(df))
k2.metric("Recurring inflows",  len(inflows))
k3.metric("Recurring outflows", len(outflows))
k4.metric(
    "Monthly committed outflow",
    f"RM {outflows[outflows['frequency'] == 'Monthly']['average_amount'].sum():,.0f}",
)

st.divider()

# ── Filters ───────────────────────────────────────────────────────────────────
f1, f2 = st.columns(2)
with f1:
    freq_filter = st.multiselect(
        "Frequency",
        options=df["frequency"].unique().tolist(),
        default=df["frequency"].unique().tolist(),
    )
with f2:
    direction = st.selectbox("Direction", ["All", "Inflow", "Outflow"])

filtered = df[df["frequency"].isin(freq_filter)]
if direction == "Inflow":
    filtered = filtered[filtered["is_inflow"] == 1]
elif direction == "Outflow":
    filtered = filtered[filtered["is_inflow"] == 0]

# ── Recurring table ───────────────────────────────────────────────────────────
st.subheader(f"Detected Patterns ({len(filtered)})")

display = filtered[[
    "description", "category", "average_amount",
    "frequency", "last_occurrence", "next_expected", "confidence", "is_inflow",
]].copy()

display["average_amount"] = display["average_amount"].map(lambda x: f"RM {x:,.2f}")
display["confidence"]     = display["confidence"].map(lambda x: f"{x:.0%}")
display["is_inflow"]      = display["is_inflow"].map(lambda x: "Inflow" if x else "Outflow")

display.columns = [
    "Description", "Category", "Avg Amount",
    "Frequency", "Last Seen", "Next Expected", "Confidence", "Direction",
]

st.dataframe(display, use_container_width=True, hide_index=True)

st.divider()

# ── Upcoming in next 30 days ──────────────────────────────────────────────────
st.subheader("Due in the Next 30 Days")

today = pd.Timestamp.today().normalize()
df["next_expected"] = pd.to_datetime(df["next_expected"])
upcoming = df[
    (df["next_expected"] >= today) &
    (df["next_expected"] <= today + pd.Timedelta(days=30))
].sort_values("next_expected")

if upcoming.empty:
    st.info("Nothing due in the next 30 days.")
else:
    for _, row in upcoming.iterrows():
        days_until = (row["next_expected"].date() - today.date()).days
        direction  = "inflow" if row["is_inflow"] else "outflow"
        colour     = "green" if row["is_inflow"] else "red"
        st.markdown(
            f"**{row['description']}** — "
            f":{colour}[RM {row['average_amount']:,.2f} {direction}] — "
            f"due in **{days_until} days** ({row['next_expected'].date()})"
        )
