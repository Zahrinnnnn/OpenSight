import sys
import os
from datetime import date, timedelta

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.analysis.recurring import (
    RecurringPayment,
    detect_recurring_payments,
    _detect_frequency,
    _group_by_similarity,
    _next_date,
)
from src.analysis.anomaly import (
    detect_large_amounts,
    detect_unusual_timing,
    detect_new_counterparties,
    detect_daily_spikes,
    detect_gaps,
    detect_anomalies,
)
from src.analysis.seasonality import (
    detect_month_end_spikes,
    detect_quarter_end_patterns,
    build_month_end_regressor,
)

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_transactions.csv")


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_df(**kwargs) -> pd.DataFrame:
    """Build a minimal transaction dataframe for testing."""
    return pd.DataFrame(kwargs)


def monthly_salary_df() -> pd.DataFrame:
    """12 monthly salary transactions, consistent amount."""
    rows = []
    base = date(2025, 4, 10)
    for i in range(12):
        month = (base.month + i - 1) % 12 + 1
        year = base.year + (base.month + i - 1) // 12
        rows.append({
            "date": date(year, month, 10),
            "description": "Salary Run - 5 Staff",
            "amount": 14200.00,
            "type": "outflow",
            "category": "Payroll",
            "id": i + 1,
        })
    return pd.DataFrame(rows)


# ── Recurring: frequency detection ───────────────────────────────────────────

def test_frequency_weekly():
    gaps = [7, 7, 7, 7]
    label, conf = _detect_frequency(gaps)
    assert label == "Weekly"
    assert conf > 0.5

def test_frequency_monthly():
    gaps = [30, 31, 30, 30]
    label, conf = _detect_frequency(gaps)
    assert label == "Monthly"
    assert conf > 0.5

def test_frequency_quarterly():
    gaps = [91, 90, 92]
    label, conf = _detect_frequency(gaps)
    assert label == "Quarterly"

def test_frequency_ad_hoc():
    # avg 15 — sits between Weekly (5-10) and Monthly (25-35), so Ad-hoc
    gaps = [10, 20, 15]
    label, conf = _detect_frequency(gaps)
    assert label == "Ad-hoc"

def test_frequency_empty_gaps():
    label, conf = _detect_frequency([])
    assert label == "Ad-hoc"
    assert conf == 0.0


# ── Recurring: description clustering ────────────────────────────────────────

def test_group_similar_descriptions():
    # In real data the same description string repeats each month
    descs = [
        "Salary Run - 5 Staff",
        "Salary Run - 5 Staff",
        "Salary Run - 5 Staff",
        "Office Rental January",
    ]
    clusters = _group_by_similarity(descs)
    # The three identical salary descriptions should cluster together
    salary_cluster = next(c for c in clusters if len(c) >= 2)
    assert len(salary_cluster) == 3

def test_group_different_descriptions():
    descs = ["Client Payment ABC", "Office Rental", "TNB Electric"]
    clusters = _group_by_similarity(descs)
    # All different — each in its own cluster
    assert len(clusters) == 3


# ── Recurring: next date calculation ─────────────────────────────────────────

def test_next_date_monthly():
    last = date(2026, 1, 10)
    nxt = _next_date(last, "Monthly", 30)
    assert nxt == date(2026, 2, 10)

def test_next_date_weekly():
    last = date(2026, 1, 10)
    nxt = _next_date(last, "Weekly", 7)
    assert nxt == last + timedelta(days=7)

def test_next_date_quarterly():
    last = date(2026, 1, 10)
    nxt = _next_date(last, "Quarterly", 91)
    assert nxt.month == 4


# ── Recurring: end-to-end on fixture ─────────────────────────────────────────

def test_detect_recurring_finds_salary():
    df = monthly_salary_df()
    results = detect_recurring_payments(df)
    assert len(results) >= 1
    salary = next((r for r in results if "salary" in r.description.lower()), None)
    assert salary is not None
    assert salary.frequency == "Monthly"
    assert salary.confidence >= 0.70

def test_detect_recurring_on_sample_fixture():
    from src.processing.cleaner import clean_transactions
    df = pd.read_csv(FIXTURE_PATH)
    df = clean_transactions(df)
    results = detect_recurring_payments(df)
    assert len(results) >= 3  # salary, rent, loan at minimum

def test_detect_recurring_is_inflow_correct():
    df = monthly_salary_df()
    results = detect_recurring_payments(df)
    for r in results:
        assert r.is_inflow is False  # salary is outflow

def test_detect_recurring_min_occurrences():
    # Only 1 occurrence should not be detected
    df = pd.DataFrame({
        "date": [date(2025, 4, 10)],
        "description": ["One-off payment"],
        "amount": [5000.00],
        "type": ["outflow"],
        "category": ["Other"],
        "id": [1],
    })
    results = detect_recurring_payments(df)
    assert len(results) == 0


# ── Anomaly: LARGE_AMOUNT ────────────────────────────────────────────────────

def test_large_amount_flagged():
    df = make_df(
        date=["2025-04-01"] * 10 + ["2025-04-15"],
        description=["Vendor Payment"] * 10 + ["Vendor Payment"],
        amount=[1000.0] * 10 + [50000.0],  # last one is a massive outlier
        type=["outflow"] * 11,
        category=["Cost of Goods"] * 11,
        id=list(range(1, 12)),
    )
    results = detect_large_amounts(df)
    assert len(results) >= 1
    assert results[0].anomaly_type == "LARGE_AMOUNT"

def test_large_amount_not_flagged_for_small_dataset():
    # Less than 4 rows in a category — skip detection
    df = make_df(
        date=["2025-04-01", "2025-04-02"],
        description=["X", "Y"],
        amount=[100.0, 200.0],
        type=["outflow", "outflow"],
        category=["Other", "Other"],
        id=[1, 2],
    )
    results = detect_large_amounts(df)
    assert len(results) == 0


# ── Anomaly: UNUSUAL_TIMING ──────────────────────────────────────────────────

def test_unusual_timing_weekend():
    # 2025-04-05 is a Saturday
    df = make_df(
        date=["2025-04-05"],
        description=["Saturday Transfer"],
        amount=[5000.0],
        type=["outflow"],
        category=["Transfer"],
        id=[1],
    )
    results = detect_unusual_timing(df)
    assert len(results) == 1
    assert "weekend" in results[0].description

def test_unusual_timing_weekday_not_flagged():
    # 2025-04-07 is a Monday
    df = make_df(
        date=["2025-04-07"],
        description=["Normal Payment"],
        amount=[1000.0],
        type=["outflow"],
        category=["Operating Expense"],
        id=[1],
    )
    results = detect_unusual_timing(df)
    assert len(results) == 0


# ── Anomaly: NEW_COUNTERPARTY ────────────────────────────────────────────────

def test_new_counterparty_flagged():
    df = make_df(
        date=["2025-04-01"],
        description=["Brand New Vendor Sdn Bhd"],
        amount=[8000.0],
        type=["outflow"],
        category=["Cost of Goods"],
        id=[1],
    )
    results = detect_new_counterparties(df)
    assert len(results) == 1
    assert results[0].anomaly_type == "NEW_COUNTERPARTY"

def test_new_counterparty_below_threshold_not_flagged():
    df = make_df(
        date=["2025-04-01"],
        description=["New Small Vendor"],
        amount=[500.0],
        type=["outflow"],
        category=["Operating Expense"],
        id=[1],
    )
    results = detect_new_counterparties(df)
    assert len(results) == 0

def test_recurring_vendor_not_flagged():
    df = make_df(
        date=["2025-04-01", "2025-05-01"],
        description=["Known Vendor Sdn Bhd", "Known Vendor Sdn Bhd"],
        amount=[8000.0, 8000.0],
        type=["outflow", "outflow"],
        category=["Cost of Goods", "Cost of Goods"],
        id=[1, 2],
    )
    results = detect_new_counterparties(df)
    assert len(results) == 0


# ── Anomaly: SPIKE ───────────────────────────────────────────────────────────

def test_spike_detected():
    # 30 normal days then one big spike
    dates = [f"2025-04-{str(i+1).zfill(2)}" for i in range(30)]
    amounts = [1000.0] * 29 + [15000.0]  # last day is a spike
    df = make_df(
        date=dates,
        description=["Daily Expense"] * 30,
        amount=amounts,
        type=["outflow"] * 30,
        category=["Operating Expense"] * 30,
        id=list(range(1, 31)),
    )
    results = detect_daily_spikes(df)
    assert len(results) >= 1
    assert results[0].anomaly_type == "SPIKE"


# ── Anomaly: GAP ─────────────────────────────────────────────────────────────

def test_gap_detected():
    df = make_df(
        date=["2025-04-01", "2025-04-15"],  # 14-day gap
        description=["A", "B"],
        amount=[1000.0, 2000.0],
        type=["outflow", "outflow"],
        category=["Other", "Other"],
        id=[1, 2],
    )
    results = detect_gaps(df)
    assert len(results) == 1
    assert results[0].anomaly_type == "GAP"
    assert "14 days" in results[0].description

def test_no_gap_for_short_break():
    df = make_df(
        date=["2025-04-01", "2025-04-05"],  # 4-day gap — under threshold
        description=["A", "B"],
        amount=[1000.0, 2000.0],
        type=["outflow", "outflow"],
        category=["Other", "Other"],
        id=[1, 2],
    )
    results = detect_gaps(df)
    assert len(results) == 0


# ── Anomaly: combined ────────────────────────────────────────────────────────

def test_detect_anomalies_runs_on_fixture():
    from src.processing.cleaner import clean_transactions
    df = pd.read_csv(FIXTURE_PATH)
    df = clean_transactions(df)
    # Add fake IDs since fixture has no DB IDs
    df["id"] = range(1, len(df) + 1)
    results = detect_anomalies(df)
    # Sample fixture has weekends and new counterparties — expect some hits
    assert isinstance(results, list)


# ── Seasonality ───────────────────────────────────────────────────────────────

def test_month_end_spike_detected():
    # Payroll always on the 28th — should count as month-end
    df = make_df(
        date=["2025-04-28", "2025-05-28", "2025-06-28",
              "2025-04-05", "2025-05-05", "2025-06-05"],
        description=["Salary Run"] * 3 + ["Vendor"] * 3,
        amount=[14200.0] * 3 + [1000.0] * 3,
        type=["outflow"] * 6,
        category=["Payroll"] * 3 + ["Payroll"] * 3,
        id=list(range(1, 7)),
    )
    result = detect_month_end_spikes(df)
    payroll = result[result["category"] == "Payroll"]
    assert not payroll.empty
    assert payroll.iloc[0]["has_spike"] == True

def test_build_month_end_regressor_column_added():
    daily = pd.DataFrame({
        "ds": pd.date_range("2025-04-01", periods=30, freq="D"),
        "y": [100.0] * 30,
    })
    result = build_month_end_regressor(daily)
    assert "month_end" in result.columns
    # April 26-30 should be month_end = 1 (last 5 days of 30-day month)
    april_30 = result[result["ds"] == pd.Timestamp("2025-04-30")]
    assert april_30.iloc[0]["month_end"] == 1

def test_quarter_end_returns_dataframe():
    from src.processing.cleaner import clean_transactions
    df = pd.read_csv(FIXTURE_PATH)
    df = clean_transactions(df)
    result = detect_quarter_end_patterns(df)
    assert isinstance(result, pd.DataFrame)
