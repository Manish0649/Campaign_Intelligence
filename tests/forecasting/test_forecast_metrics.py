import numpy as np
import pandas as pd

from scripts.forecasting.forecast_pipeline import compute_errors


def test_error_metrics_report_wape_and_handle_zero_actuals():
    forecasts = pd.DataFrame({
        "product_id": ["A", "A", "B"],
        "ds": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-01"]),
        "forecast": [2.0, 1.0, 0.0],
        "model": ["test"] * 3,
    })
    actual = pd.DataFrame({
        "product_id": ["A", "A", "B"],
        "ds": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-01"]),
        "demand": [1.0, 0.0, 0.0],
    })

    result = compute_errors(forecasts, actual)
    overall = result[result["product_id"] == "ALL"].iloc[0]

    assert overall["mae"] == 2.0 / 3.0
    assert np.isfinite(overall["rmse"])
    assert overall["wape_pct"] == 200.0
    assert overall["zero_actual_observations"] == 2
    assert overall["mape_pct_nonzero_only"] == 100.0


def test_error_metrics_reject_non_overlapping_dates():
    forecasts = pd.DataFrame({
        "product_id": ["A"], "ds": pd.to_datetime(["2020-01-01"]),
        "forecast": [1.0], "model": ["test"],
    })
    actual = pd.DataFrame({
        "product_id": ["A"], "ds": pd.to_datetime(["2020-01-02"]),
        "demand": [1.0],
    })
    try:
        compute_errors(forecasts, actual)
    except ValueError as exc:
        assert "No overlapping" in str(exc)
    else:
        raise AssertionError("Expected non-overlapping data to fail evaluation.")
