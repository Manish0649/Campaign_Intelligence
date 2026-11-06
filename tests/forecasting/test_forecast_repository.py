from datetime import date

import pytest

from backend.app.db.repositories.forecast_repo import (
    FORECAST_MODEL,
    ForecastNotFoundError,
    ForecastRepository,
)


def test_generates_custom_future_dates_and_non_constant_daily_values():
    result = ForecastRepository().get_forecast(
        product_id="FOODS_1_018",
        start_date=date(2026, 11, 7),
        horizon_days=7,
        model=FORECAST_MODEL,
    )
    assert result.model == "linear_regression"
    assert result.horizon_days == 7
    assert [point.date for point in result.daily_forecasts] == [
        date(2026, 11, day) for day in range(7, 14)
    ]
    values = [point.forecast_units for point in result.daily_forecasts]
    assert all(value >= 0 for value in values)
    assert len(set(values)) > 1
    assert result.total_forecast_units == round(sum(values), 2)


def test_rejects_unknown_product_without_fallback():
    with pytest.raises(ForecastNotFoundError, match="No historical demand"):
        ForecastRepository().get_forecast(
            product_id="UNKNOWN_PRODUCT",
            start_date=date(2026, 11, 7),
            horizon_days=7,
        )


def test_rejects_dates_before_historical_origin():
    with pytest.raises(ValueError, match="must be after the latest historical date"):
        ForecastRepository().get_forecast(
            product_id="FOODS_1_018",
            start_date=date(2016, 4, 24),
            horizon_days=2,
        )


def test_rejects_non_selected_model():
    with pytest.raises(ValueError, match="Unsupported forecast model"):
        ForecastRepository().get_forecast(
            product_id="FOODS_1_018",
            start_date=date(2026, 11, 7),
            horizon_days=7,
            model="naive",
        )
