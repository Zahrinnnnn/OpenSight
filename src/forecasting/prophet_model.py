import os
from pathlib import Path

import pandas as pd
from prophet import Prophet

from src.utils.logger import logger
from src.analysis.seasonality import build_month_end_regressor


MODEL_DIR = os.getenv("MODEL_DIR", "data/models")


def train_forecast_model(daily_df: pd.DataFrame) -> Prophet:
    """
    Train a Prophet model on daily net cash flow data.
    Expects a dataframe with 'ds' and 'y' columns.
    Adds Malaysian public holidays and a month-end regressor.
    """
    daily_df = build_month_end_regressor(daily_df)

    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        seasonality_mode="multiplicative",
        changepoint_prior_scale=0.05,
        seasonality_prior_scale=10,
        interval_width=0.80,
    )

    # Malaysian public holidays
    model.add_country_holidays(country_name="MY")

    # Month-end effect — salary, rent, utilities tend to cluster here
    model.add_regressor("month_end")

    logger.info(f"Training Prophet model on {len(daily_df)} days of data")
    model.fit(daily_df)
    logger.success("Prophet model trained")

    return model


def generate_forecast(model: Prophet, daily_df: pd.DataFrame, horizon_days: int = 90) -> pd.DataFrame:
    """
    Generate a forecast for the given number of days ahead.
    Returns a dataframe with ds, yhat, yhat_lower, yhat_upper, trend, month_end.
    """
    future = model.make_future_dataframe(periods=horizon_days)
    future = build_month_end_regressor(future)

    forecast = model.predict(future)

    # Keep only the columns we need
    cols = ["ds", "yhat", "yhat_lower", "yhat_upper", "trend"]
    # weekly/yearly seasonality components may not always exist by these names
    for comp in ["weekly", "yearly", "holidays"]:
        if comp in forecast.columns:
            cols.append(comp)

    return forecast[cols].copy()


def save_model(model: Prophet, run_id: int) -> str:
    """Serialise the trained model to disk. Returns the file path."""
    import pickle

    Path(MODEL_DIR).mkdir(parents=True, exist_ok=True)
    path = str(Path(MODEL_DIR) / f"prophet_run_{run_id}.pkl")

    with open(path, "wb") as f:
        pickle.dump(model, f)

    logger.info(f"Model saved to {path}")
    return path


def load_model(path: str) -> Prophet:
    import pickle
    with open(path, "rb") as f:
        return pickle.load(f)
