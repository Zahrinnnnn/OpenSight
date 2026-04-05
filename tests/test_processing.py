import sys
import os
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.processing.cleaner import clean_transactions, clean_amount, parse_date
from src.processing.categoriser import categorise_by_rules, categorise_transactions
from src.processing.aggregator import aggregate_daily, get_monthly_summary


FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_transactions.csv")


# ── Cleaner tests ─────────────────────────────────────────────────────────────

def test_clean_amount_strips_rm():
    assert clean_amount("RM 1,200.50") == 1200.50

def test_clean_amount_strips_commas():
    assert clean_amount("14,200.00") == 14200.00

def test_clean_amount_always_positive():
    assert clean_amount("-500.00") == 500.00

def test_parse_date_iso():
    result = parse_date("2025-04-10")
    assert result.year == 2025
    assert result.month == 4
    assert result.day == 10

def test_parse_date_slash_format():
    result = parse_date("10/04/2025")
    assert result is not None
    assert result.year == 2025

def test_parse_date_invalid():
    result = parse_date("not-a-date")
    assert pd.isna(result)

def test_clean_transactions_removes_duplicates():
    df = pd.DataFrame({
        "date": ["2025-04-10", "2025-04-10"],
        "description": ["Salary Run", "Salary Run"],
        "amount": [14200.00, 14200.00],
        "type": ["outflow", "outflow"],
    })
    result = clean_transactions(df)
    assert len(result) == 1

def test_clean_transactions_normalises_type():
    df = pd.DataFrame({
        "date": ["2025-04-10"],
        "description": ["Client Payment"],
        "amount": [5000.00],
        "type": ["credit"],
    })
    result = clean_transactions(df)
    assert result.iloc[0]["type"] == "inflow"

def test_clean_transactions_drops_bad_dates():
    df = pd.DataFrame({
        "date": ["not-a-date", "2025-04-10"],
        "description": ["Bad row", "Good row"],
        "amount": [100.00, 200.00],
        "type": ["outflow", "outflow"],
    })
    result = clean_transactions(df)
    assert len(result) == 1
    assert result.iloc[0]["description"] == "Good row"

def test_clean_transactions_sorted_ascending():
    df = pd.DataFrame({
        "date": ["2025-06-01", "2025-04-01", "2025-05-01"],
        "description": ["C", "A", "B"],
        "amount": [100.0, 200.0, 300.0],
        "type": ["outflow", "outflow", "outflow"],
    })
    result = clean_transactions(df)
    dates = result["date"].tolist()
    assert dates == sorted(dates)

def test_clean_loads_sample_fixture():
    df = pd.read_csv(FIXTURE_PATH)
    cleaned = clean_transactions(df)
    assert len(cleaned) > 100
    assert set(cleaned["type"].unique()).issubset({"inflow", "outflow"})


# ── Categoriser tests ─────────────────────────────────────────────────────────

def test_rule_salary():
    assert categorise_by_rules("Salary Run April - 5 Staff") == "Payroll"

def test_rule_gaji():
    assert categorise_by_rules("Bayaran Gaji Mei") == "Payroll"

def test_rule_rent():
    assert categorise_by_rules("Office Rental January 2026") == "Rent"

def test_rule_sewa():
    assert categorise_by_rules("Sewa Pejabat Februari") == "Rent"

def test_rule_utilities_tnb():
    assert categorise_by_rules("TNB Electric Bill March") == "Utilities"

def test_rule_utilities_unifi():
    assert categorise_by_rules("Unifi Business Broadband April") == "Utilities"

def test_rule_tax_lhdn():
    assert categorise_by_rules("LHDN Tax Payment Q1") == "Tax"

def test_rule_loan():
    assert categorise_by_rules("CIMB Business Loan Instalment") == "Loan Repayment"

def test_rule_insurance():
    assert categorise_by_rules("Prudential Insurance Premium") == "Insurance"

def test_rule_refund():
    assert categorise_by_rules("Refund from Apex Supplies") == "Refund"

def test_rule_transfer():
    assert categorise_by_rules("DuitNow Transfer to Supplier") == "Transfer"

def test_rule_dividend():
    assert categorise_by_rules("Dividend Payment Q3") == "Dividend"

def test_rule_no_match():
    assert categorise_by_rules("Random mystery payment") is None

def test_categorise_transactions_rule_based_only():
    df = pd.DataFrame({
        "date": ["2025-04-10", "2025-04-05"],
        "description": ["Salary Run April", "Office Rental April"],
        "amount": [14200.00, 3500.00],
        "type": ["outflow", "outflow"],
        "category": [None, None],
    })
    result = categorise_transactions(df, use_deepseek=False)
    assert result.iloc[0]["category"] == "Payroll"
    assert result.iloc[1]["category"] == "Rent"

def test_categorise_preserves_existing_category():
    df = pd.DataFrame({
        "date": ["2025-04-10"],
        "description": ["Some payment"],
        "amount": [5000.00],
        "type": ["outflow"],
        "category": ["CAPEX"],
    })
    result = categorise_transactions(df, use_deepseek=False)
    assert result.iloc[0]["category"] == "CAPEX"

def test_categorise_unmatched_without_deepseek():
    df = pd.DataFrame({
        "date": ["2025-04-10"],
        "description": ["Mystery vendor payment"],
        "amount": [999.00],
        "type": ["outflow"],
        "category": [None],
    })
    result = categorise_transactions(df, use_deepseek=False)
    assert result.iloc[0]["category"] == "Other"


# ── Aggregator tests ──────────────────────────────────────────────────────────

def test_aggregate_daily_columns():
    df = pd.DataFrame({
        "date": ["2025-04-10", "2025-04-10", "2025-04-11"],
        "description": ["Salary", "Client", "Rent"],
        "amount": [14200.00, 18500.00, 3500.00],
        "type": ["outflow", "inflow", "outflow"],
    })
    result = aggregate_daily(df)
    assert "ds" in result.columns
    assert "y" in result.columns

def test_aggregate_daily_net_flow():
    df = pd.DataFrame({
        "date": ["2025-04-10", "2025-04-10"],
        "description": ["Client Payment", "Salary Run"],
        "amount": [18500.00, 14200.00],
        "type": ["inflow", "outflow"],
    })
    result = aggregate_daily(df)
    row = result[result["ds"] == pd.Timestamp("2025-04-10")]
    assert abs(row.iloc[0]["y"] - 4300.00) < 0.01

def test_aggregate_fills_missing_days():
    df = pd.DataFrame({
        "date": ["2025-04-01", "2025-04-05"],
        "description": ["A", "B"],
        "amount": [1000.00, 2000.00],
        "type": ["inflow", "outflow"],
    })
    result = aggregate_daily(df)
    # Should have 5 rows: Apr 1, 2, 3, 4, 5
    assert len(result) == 5

def test_aggregate_sorted_ascending():
    df = pd.DataFrame({
        "date": ["2025-04-05", "2025-04-01"],
        "description": ["B", "A"],
        "amount": [1000.00, 2000.00],
        "type": ["outflow", "inflow"],
    })
    result = aggregate_daily(df)
    assert result.iloc[0]["ds"] < result.iloc[-1]["ds"]

def test_monthly_summary_columns():
    df = pd.read_csv(FIXTURE_PATH)
    cleaned = clean_transactions(df)
    summary = get_monthly_summary(cleaned)
    assert "month" in summary.columns
    assert "inflow" in summary.columns
    assert "outflow" in summary.columns
    assert "net" in summary.columns

def test_monthly_summary_net_calculation():
    df = pd.DataFrame({
        "date": ["2025-04-10", "2025-04-15"],
        "description": ["Client", "Salary"],
        "amount": [10000.00, 6000.00],
        "type": ["inflow", "outflow"],
        "category": ["Revenue", "Payroll"],
    })
    summary = get_monthly_summary(df)
    assert abs(summary.iloc[0]["net"] - 4000.00) < 0.01
