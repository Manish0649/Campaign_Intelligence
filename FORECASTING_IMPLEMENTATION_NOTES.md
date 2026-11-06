# Forecasting implementation notes

## Runtime API behavior

The runtime API no longer reads `data/forecast/forecast_horizon_7d.csv` for user requests. `ForecastRepository` trains a per-product linear-regression model from historical daily demand in `data/processed/m5_processed_features.csv` and generates predictions on demand for a user-selected future date range.

Supported behavior:
- Model: `linear_regression`
- User-selected start date after the latest historical observation for the requested product
- Horizon: 1–30 days
- Forecast lead: up to 7,300 days from the historical origin
- Features: trend, weekday, weekly and annual seasonality, lag demand, and rolling demand statistics
- A recent weekday-average blend retains weekly retail seasonality and prevents the API from repeating one identical scalar prediction across the whole horizon
- Unknown products and invalid dates are rejected; no fabricated product history is used

Example:

```http
GET /products/FOODS_1_018/forecast?start_date=2026-11-07&horizon_days=7
```

The response dates are generated from the requested start date, not looked up from a fixed forecast calendar.

## Offline evaluation pipeline

`scripts/forecasting/forecast_pipeline.py` remains an offline model-validation utility. It performs a chronological holdout evaluation and may still write `data/forecast/forecast_horizon_7d.csv` for reproducibility. That generated file is not the source used by the runtime forecast API.
