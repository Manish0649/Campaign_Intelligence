# Forecast Validation and Leakage Audit — Current Pipeline Run

## Scope and data window

- Source: 500 M5 benchmark products from `fct_daily_sales.csv`.
- Raw observations: 182,500 product-day rows (2015-04-26 through 2016-04-24).
- Feature rows after warm-up removal: 165,500.
- Warm-up removal: 34 initial observations per product are excluded so the 28-day rolling window, offset by the 7-day forecast horizon, is fully populated.
- Production forecast: 2016-04-25 through 2016-05-01, based on history through 2016-04-24.

## Leakage controls

- Direct demand lags: 7, 14, 21 and 28 days.
- Rolling demand statistics are calculated within each product group using a minimum lag offset of 7 days.
- The 7-day and 28-day rolling features require complete windows (7 and 28 observations respectively).
- Product groups are isolated with `groupby(...).transform(...)`; a product's rolling history cannot bleed into the next product's rows.
- Rows without a complete 28-day rolling feature are removed before model training.

Automated coverage: `tests/validation/test_feature_engineering_group_boundaries.py` checks product-boundary isolation and warm-up behavior; `tests/validation/test_forecast_validation.py` checks horizon lag constraints and chronological ordering.

## Chronological holdout

- Training cutoff: 2016-03-25.
- Validation set: the following 30 days (2016-03-26 through 2016-04-24).
- Evaluation horizon: first 7 days of that holdout (2016-03-26 through 2016-04-01).
- Evaluation size: 3,500 product-day observations (500 products × 7 days).
- Zero-actual observations: 495 (14.14%); therefore MAPE is reported only as a diagnostic on non-zero actuals.

## Aggregate benchmark metrics

| Model | MAE (units) | RMSE (units) | WAPE | sMAPE | MAPE (non-zero actuals only) |
|---|---:|---:|---:|---:|---:|
| Linear regression | 2.9981 | 5.3382 | 56.2681% | 74.8126% | 66.8654% |
| Moving average | 2.9720 | 5.0721 | 55.7770% | 72.7678% | 74.1448% |
| Naive | 3.7160 | 6.0283 | 69.7410% | 89.0288% | 99.1148% |

On this single holdout, moving average is slightly better than linear regression on MAE, RMSE, WAPE and sMAPE. This is not enough evidence to change the API's configured `linear_regression` model: a broader rolling-origin evaluation should be performed before promoting a different model to production. The naive baseline is weaker on the aggregate metrics.

## Interpretation and limitations

- WAPE is the primary aggregate percentage metric because it includes zero-sales observations in the denominator at the aggregate level (when total demand is non-zero).
- MAPE excludes zero-actual rows and can be highly unstable for low-volume items; it must not be used alone.
- Forecast values are estimates of baseline demand, not measured campaign uplift or causal incremental sales.
- The uplift percentage supplied to feasibility is a scenario assumption, not a learned causal effect.
- This benchmark is one chronological holdout, not a full rolling-origin backtest.
- `data/forecast/forecast_horizon_7d.csv` contains 10,500 rows: 500 products × 7 days × 3 model outputs. The API currently serves `linear_regression`.

## Reproduction

```powershell
python scripts/build_m5_features.py
python scripts/forecasting/forecast_pipeline.py
pytest -q tests/validation/test_feature_engineering_group_boundaries.py tests/forecasting/test_forecast_metrics.py
```
