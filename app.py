import streamlit as st

st.set_page_config(
    page_title="OpenSight",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Page registry
pages = {
    "Home":              "ui/pages/home.py",
    "Overview":          "ui/pages/overview.py",
    "Forecast":          "ui/pages/forecast.py",
    "Inflow / Outflow":  "ui/pages/cashflow.py",
    "Recurring":         "ui/pages/recurring.py",
    "Anomalies":         "ui/pages/anomalies.py",
    "Narrative":         "ui/pages/narrative.py",
    "History":           "ui/pages/history.py",
}

with st.sidebar:
    st.markdown("## 📊 OpenSight")
    st.markdown("Cash Flow Forecasting Engine")
    st.divider()
    selection = st.radio("Navigate", list(pages.keys()), label_visibility="collapsed")
    st.divider()
    st.caption("Built with Prophet · DeepSeek · Streamlit")

# Load and run the selected page module
page_file = pages[selection]
with open(page_file, encoding="utf-8") as f:
    code = f.read()
exec(compile(code, page_file, "exec"), {"__name__": "__main__"})
