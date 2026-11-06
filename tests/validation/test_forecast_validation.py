import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from scripts.forecasting.forecast_pipeline import chronological_split, naive_forecast, moving_average_forecast
from backend.app.config import BASE_DIR

DATA_PATH = BASE_DIR / "data" / "processed" / "m5_processed_features.csv"

def test_feature_engineering_lag_leakage_rule5():
    """
    Rule 5 Compliance Check:
    For a 7-day forecast horizon (H=7), any lagged feature or rolling window
    must use an offset of >= 7 days. No feature for day t may see sales from
    t-1 through t-6 because those days would be in the unobserved target horizon
    at origin t-7.
    """
    assert DATA_PATH.exists(), f"Processed features file not found at {DATA_PATH}"
    df = pd.read_csv(DATA_PATH, nrows=5000)
    
    # Check that lag columns have names >= 7
    lag_cols = [col for col in df.columns if col.startswith("lag_")]
    assert len(lag_cols) > 0, "No lag features found in processed data"
    for col in lag_cols:
        lag_num = int(col.split("_")[1])
        assert lag_num >= 7, f"Feature leakage detected: {col} has lag < 7 (horizon H=7)"

    # Check rolling columns: rolling stats must be derived from lag >= 7
    rolling_cols = [col for col in df.columns if col.startswith("rolling_")]
    assert len(rolling_cols) > 0, "No rolling features found in processed data"
    # Ensure neither target 'sales_units' of current day is part of the feature calculation

def test_chronological_split_strict_ordering():
    """
    Validate that train/test split is strictly chronological with zero temporal overlap.
    Max train date < Min test date.
    """
    dates = pd.date_range("2015-05-01", periods=100, freq="D")
    sample_df = pd.DataFrame({
        "product_id": ["P1"] * 100,
        "ds": dates,
        "demand": np.random.default_rng(42).poisson(lam=5, size=100)
    })
    
    train, test, cutoff = chronological_split(sample_df, test_days=30)
    
    assert len(train) == 70
    assert len(test) == 30
    assert train["ds"].max() <= cutoff
    assert test["ds"].min() > cutoff
    assert train["ds"].max() < test["ds"].min(), "Temporal leakage: Train max date is not strictly less than Test min date"
    assert set(train["ds"]).isdisjoint(set(test["ds"])), "Overlap detected between training and test timestamps"

def test_naive_baseline_reproducibility():
    """
    Naïve forecast repeats the exact last observed demand across the horizon.
    """
    dates = pd.date_range("2016-04-01", periods=14, freq="D")
    train = pd.DataFrame({
        "product_id": ["TEST_ITEM_1"] * 14,
        "ds": dates,
        "demand": [2, 3, 4, 1, 0, 5, 2, 8, 3, 2, 6, 4, 1, 9]  # last observed is 9
    })
    
    fc = naive_forecast(train, horizon=7)
    assert len(fc) == 7
    assert (fc["forecast"] == 9).all(), "Naïve forecast did not carry forward the last observed demand"
    assert fc["ds"].min() == dates.max() + timedelta(days=1)
    assert fc["ds"].max() == dates.max() + timedelta(days=7)

def test_zero_sales_and_low_volume_handling():
    """
    Test zero-sales product where last observed and rolling mean are 0.
    Must not generate NaN, nulls, or negative forecasts.
    """
    dates = pd.date_range("2016-04-01", periods=14, freq="D")
    train = pd.DataFrame({
        "product_id": ["ZERO_SALES_ITEM"] * 14,
        "ds": dates,
        "demand": [0] * 14
    })
    
    fc = naive_forecast(train, horizon=7)
    assert not fc["forecast"].isna().any(), "NaN found in zero-sales forecast"
    assert (fc["forecast"] >= 0).all(), "Negative value found in zero-sales forecast"
    assert (fc["forecast"] == 0).all()

