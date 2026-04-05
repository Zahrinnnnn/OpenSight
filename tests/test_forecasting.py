import sys
import os
from datetime import date, timedelta

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.forecasting.prophet_model import train_forecast_model, generate_forecast
from src.forecasting.shortfall import (
    calculate_cash_position,
    detect_shortfalls,
    get_forecast_summary,
    Shortfall,
)
from src.analysis.seasonality import build_month_end_regressor

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_transactions.csv")


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_daily_df(days: int = 180, net_per_day: float = 500.0) -> pd.DataFrame:
    """Build a synthetic daily dataframe with consistent positive net flow."""
    dates = pd.date_range(
        start=pd.Timestamp.today() - pd.Timedelta(days=days),
        periods=days,
        freq="D",
    )
    return pd.DataFrame({"ds": dates, "y": [net_per_day] * days})


def make_forecast_df(days_ahead: int = 90, daily_net: float = 500.0) -> pd.DataFrame:
    """Build a synthetic forecast dataframe (future dates only)."""
    today = pd.Timestamp.today().normalize()
    dates = pd.date_range(start=today + pd.Timedelta(days=1), periods=days_ahead, freq="D")
    return pd.DataFrame({
        "ds": dates,
        "yhat": [daily_net] * days_ahead,
        "yhat_lower": [daily_net * 0.8] * days_ahead,
        "yhat_upper": [daily_net * 1.2] * days_ahead,
        "trend": [daily_net] * days_ahead,
    })


def make_deficit_forecast_df(days_ahead: int = 90) -> pd.DataFrame:
    """Forecast that burns cash every day — should produce shortfalls."""
    today = pd.Timestamp.today().normalize()
    dates = pd.date_range(start=today + pd.Timedelta(days=1), periods=days_ahead, freq="D")
    return pd.DataFrame({
        "ds": dates,
        "yhat": [-1000.0] * days_ahead,
        "yhat_lower": [-1200.0] * days_ahead,
        "yhat_upper": [-800.0] * days_ahead,
        "trend": [-1000.0] * days_ahead,
    })


# ── Prophet model training ────────────────────────────────────────────────────

def test_train_model_returns_prophet():
    from prophet import Prophet
    daily = make_daily_df(days=180)
    model = train_forecast_model(daily)
    assert isinstance(model, Prophet)


def test_train_model_adds_month_end_regressor():
    from prophet import Prophet
    daily = make_daily_df(days=180)
    model = train_forecast_model(daily)
    assert "month_end" in model.extra_regressors


def test_generate_forecast_columns():
    daily = make_daily_df(days=180)
    model = train_forecast_model(daily)
    forecast = generate_forecast(model, daily, horizon_days=90)
    for col in ["ds", "yhat", "yhat_lower", "yhat_upper"]:
        assert col in forecast.columns


def test_generate_forecast_90_day_length():
    daily = make_daily_df(days=180)
    model = train_forecast_model(daily)
    forecast = generate_forecast(model, daily, horizon_days=90)
    # Total rows = historical + 90 forecast days
    assert len(forecast) == len(daily) + 90


def test_generate_forecast_30_days():
    daily = make_daily_df(days=180)
    model = train_forecast_model(daily)
    forecast = generate_forecast(model, daily, horizon_days=30)
    assert len(forecast) == len(daily) + 30


def test_yhat_lower_lte_yhat():
    daily = make_daily_df(days=180)
    model = train_forecast_model(daily)
    forecast = generate_forecast(model, daily, horizon_days=90)
    assert (forecast["yhat_lower"] <= forecast["yhat"]).all()


def test_yhat_upper_gte_yhat():
    daily = make_daily_df(days=180)
    model = train_forecast_model(daily)
    forecast = generate_forecast(model, daily, horizon_days=90)
    assert (forecast["yhat_upper"] >= forecast["yhat"]).all()


def test_train_on_sample_fixture():
    """Full end-to-end: load fixture, clean, aggregate, train, forecast."""
    from src.processing.cleaner import clean_transactions
    from src.processing.aggregator import aggregate_daily

    df = pd.read_csv(FIXTURE_PATH)
    cleaned = clean_transactions(df)
    daily = aggregate_daily(cleaned)
    model = train_forecast_model(daily)
    forecast = generate_forecast(model, daily, horizon_days=90)
    assert len(forecast) > 0
    assert "yhat" in forecast.columns


# ── Cash position calculation ─────────────────────────────────────────────────

def test_cash_position_columns_added():
    fc = make_forecast_df()
    result = calculate_cash_position(fc, opening_balance=10000.0)
    for col in ["cash_position", "worst_case", "best_case"]:
        assert col in result.columns


def test_cash_position_starts_from_opening_balance():
    fc = make_forecast_df(days_ahead=90, daily_net=100.0)
    result = calculate_cash_position(fc, opening_balance=5000.0)
    # First row: opening + first day net
    assert abs(result.iloc[0]["cash_position"] - 5100.0) < 1.0


def test_cash_position_cumulative():
    fc = make_forecast_df(days_ahead=3, daily_net=1000.0)
    result = calculate_cash_position(fc, opening_balance=0.0)
    assert abs(result.iloc[2]["cash_position"] - 3000.0) < 1.0


def test_worst_case_lte_cash_position():
    fc = make_forecast_df()
    result = calculate_cash_position(fc, opening_balance=10000.0)
    assert (result["worst_case"] <= result["cash_position"]).all()


def test_best_case_gte_cash_position():
    fc = make_forecast_df()
    result = calculate_cash_position(fc, opening_balance=10000.0)
    assert (result["best_case"] >= result["cash_position"]).all()


# ── Shortfall detection ───────────────────────────────────────────────────────

def test_shortfall_detected_when_balance_drops():
    fc = make_deficit_forecast_df()
    fc = calculate_cash_position(fc, opening_balance=5000.0)
    shortfalls = detect_shortfalls(fc, minimum_balance=0, alert_threshold=0)
    assert len(shortfalls) > 0


def test_shortfall_not_detected_when_healthy():
    fc = make_forecast_df(daily_net=1000.0)
    fc = calculate_cash_position(fc, opening_balance=50000.0)
    shortfalls = detect_shortfalls(fc, minimum_balance=0, alert_threshold=0)
    assert len(shortfalls) == 0


def test_shortfall_has_correct_fields():
    fc = make_deficit_forecast_df()
    fc = calculate_cash_position(fc, opening_balance=3000.0)
    shortfalls = detect_shortfalls(fc, minimum_balance=0, alert_threshold=0)
    assert len(shortfalls) > 0
    s = shortfalls[0]
    assert isinstance(s.shortfall_date, date)
    assert isinstance(s.projected_balance, float)
    assert isinstance(s.days_until, int)
    assert s.days_until >= 0


def test_shortfall_raises_without_cash_position():
    fc = make_forecast_df()  # no cash_position column
    with pytest.raises(ValueError):
        detect_shortfalls(fc)


def test_alert_threshold_triggers_shortfall():
    # Balance stays above 0 but dips below 5000 — should trigger on alert_threshold
    fc = make_forecast_df(daily_net=-50.0)
    fc = calculate_cash_position(fc, opening_balance=2000.0)
    shortfalls = detect_shortfalls(fc, minimum_balance=0, alert_threshold=5000)
    assert len(shortfalls) > 0


# ── Forecast summary ──────────────────────────────────────────────────────────

def test_forecast_summary_keys():
    fc = make_forecast_df()
    fc = calculate_cash_position(fc, opening_balance=10000.0)
    summary = get_forecast_summary(fc, opening_balance=10000.0)
    for key in ["forecast_30", "forecast_60", "forecast_90", "closing_balance"]:
        assert key in summary


def test_forecast_summary_30_lte_60_lte_90_positive():
    # With consistent positive net, cumulative should grow
    fc = make_forecast_df(days_ahead=90, daily_net=500.0)
    fc = calculate_cash_position(fc, opening_balance=0.0)
    summary = get_forecast_summary(fc, opening_balance=0.0)
    assert summary["forecast_30"] <= summary["forecast_60"] <= summary["forecast_90"]


def test_closing_balance_positive_for_positive_flow():
    fc = make_forecast_df(daily_net=1000.0)
    fc = calculate_cash_position(fc, opening_balance=10000.0)
    summary = get_forecast_summary(fc, opening_balance=10000.0)
    assert summary["closing_balance"] > 10000.0


# ── Month-end regressor ───────────────────────────────────────────────────────

def test_month_end_regressor_on_future_dates():
    future = pd.DataFrame({
        "ds": pd.date_range("2026-04-01", periods=30, freq="D"),
        "yhat": [0.0] * 30,
        "yhat_lower": [0.0] * 30,
        "yhat_upper": [0.0] * 30,
        "trend": [0.0] * 30,
    })
    result = build_month_end_regressor(future)
    assert "month_end" in result.columns
    # April 26-30 should be flagged
    end_days = result[result["ds"] >= pd.Timestamp("2026-04-26")]
    assert end_days["month_end"].sum() == 5
