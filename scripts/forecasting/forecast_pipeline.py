"""
Forecasting pipeline – Day 3

This module implements:
* Naïve baseline (last observed value)
* Simple moving‑average baseline (7‑day window)
* Optional linear‑regression model using the engineered lag features

All models are evaluated on a chronological validation split (train up to
the day before the last 30 days, test = last 30 days).  Forecast errors
(MAE, MAPE) are computed per product and aggregated.

Outputs are written to:
    data/forecast/forecast_horizon_7d.csv
    docs/forecasting_report.md
"""

import os
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def load_data() -> pd.DataFrame:
    """Load the processed M5 feature file.

    The stored CSV uses the column name ``date`` for the timestamp and
    ``sales_units`` for the target demand.  This function reads the file,
    converts ``date`` to a proper datetime column named ``ds`` (the naming
    convention used throughout the forecasting code), and creates a ``demand``
    column as an alias of ``sales_units``.
    """
    data_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "processed", "m5_processed_features.csv"
    )
    # Read without parsing dates first – we will handle the column rename.
    df = pd.read_csv(data_path)
    # Rename and parse the date column to ``ds``
    df = df.rename(columns={"date": "ds", "sales_units": "demand"})
    df["ds"] = pd.to_datetime(df["ds"])
    df = df.sort_values(["product_id", "ds"]).reset_index(drop=True)
    return df


def chronological_split(df: pd.DataFrame, test_days: int = 30):
    """Split the data chronologically.

    The most recent ``test_days`` are used as the test set, the rest as training.
    """
    max_date = df["ds"].max()
    cutoff = max_date - pd.Timedelta(days=test_days)
    train = df[df["ds"] <= cutoff].copy()
    test = df[df["ds"] > cutoff].copy()
    return train, test, cutoff

# ---------------------------------------------------------------------------
# Baseline models
# ---------------------------------------------------------------------------

def naive_forecast(train: pd.DataFrame, horizon: int = 7) -> pd.DataFrame:
    """Naïve forecast – repeat the last observed demand for each product.

    Parameters
    ----------
    train: pd.DataFrame
        Training data (chronological order required).
    horizon: int, default 7
        Number of days to forecast.
    """
    last_obs = (
        train.sort_values("ds")
        .groupby("product_id", as_index=False)
        .tail(1)[["product_id", "demand"]]
        .rename(columns={"demand": "forecast"})
    )
    # generate future dates based on the max date in train
    start_date = train["ds"].max() + pd.Timedelta(days=1)
    forecast_rows = []
    for _, row in last_obs.iterrows():
        for i in range(horizon):
            forecast_rows.append({
                "product_id": row["product_id"],
                "ds": start_date + pd.Timedelta(days=i),
                "forecast": row["forecast"],
                "model": "naive",
            })
    return pd.DataFrame(forecast_rows)


def moving_average_forecast(train: pd.DataFrame, horizon: int = 7, window: int = 7) -> pd.DataFrame:
    """Simple moving‑average forecast.

    The average of the last ``window`` days of demand per product is used as the
    constant forecast for the next ``horizon`` days.
    """
    # compute rolling mean per product (including the current day)
    recent = (
        train.sort_values("ds")
        .groupby("product_id", group_keys=False)
        .tail(window)
    )
    ma = (
        recent.groupby("product_id", as_index=False)["demand"]
        .mean()
        .rename(columns={"demand": "forecast"})
    )
    start_date = train["ds"].max() + pd.Timedelta(days=1)
    rows = []
    for _, row in ma.iterrows():
        for i in range(horizon):
            rows.append({
                "product_id": row["product_id"],
                "ds": start_date + pd.Timedelta(days=i),
                "forecast": row["forecast"],
                "model": "moving_average",
            })
    return pd.DataFrame(rows)

# ---------------------------------------------------------------------------
# Optional linear‑regression model using lag features
# ---------------------------------------------------------------------------

def linear_regression_forecast(train: pd.DataFrame, test: pd.DataFrame, horizon: int = 7) -> pd.DataFrame:
    """Train a LinearRegression on the engineered features and predict the test set.

    The model is fit on all rows of ``train`` and then used to predict the next
    ``horizon`` days for each product based on the latest available feature row.
    Non‑numeric columns (e.g., ``store_id``, ``event_name``) are excluded because
    ``sklearn`` cannot handle them directly.
    """
    # Identify numeric feature columns (exclude identifiers and target)
    non_feature = {"product_id", "ds", "demand"}
    numeric_cols = [c for c in train.select_dtypes(include="number").columns if c not in non_feature]
    # In case some engineered features are still object type, coerce them to numeric
    X_train = train[numeric_cols].apply(pd.to_numeric, errors="coerce")
    X_train = X_train.replace([np.inf, -np.inf], np.nan)
    X_train = X_train.dropna(axis=1, how="all")
    numeric_cols = list(X_train.columns)
    if not numeric_cols:
        raise ValueError("No usable numeric features are available for linear regression.")
    y_train = pd.to_numeric(train["demand"], errors="coerce")
    valid_rows = y_train.notna() & np.isfinite(y_train)
    X_train = X_train.loc[valid_rows]
    y_train = y_train.loc[valid_rows].astype(float)
    if X_train.empty:
        raise ValueError("No valid training rows are available for linear regression.")
    # Median imputation is less sensitive to retail demand outliers than mean imputation.
    feature_medians = X_train.median().fillna(0.0)
    X_train = X_train.fillna(feature_medians)
    lr = LinearRegression(n_jobs=4)
    lr.fit(X_train, y_train)

    # For forecasting we need the most recent numeric feature row per product.
    latest_features = (
        train.sort_values("ds")
        .groupby("product_id")
        .tail(1)[["product_id"] + numeric_cols]
    )
    X_latest = latest_features[numeric_cols].apply(pd.to_numeric, errors="coerce")
    X_latest = X_latest.replace([np.inf, -np.inf], np.nan).fillna(feature_medians)
    preds = np.maximum(0.0, lr.predict(X_latest))
    start_date = train["ds"].max() + pd.Timedelta(days=1)
    rows = []
    for pid, pred in zip(latest_features["product_id"], preds):
        for i in range(horizon):
            rows.append({
                "product_id": pid,
                "ds": start_date + pd.Timedelta(days=i),
                "forecast": float(pred),
                "model": "linear_regression",
            })
    return pd.DataFrame(rows)

# ---------------------------------------------------------------------------
# Evaluation utilities
# ---------------------------------------------------------------------------

def compute_errors(forecasts: pd.DataFrame, actual: pd.DataFrame) -> pd.DataFrame:
    """Calculate MAE, RMSE, WAPE, sMAPE and diagnostic MAPE.

    MAPE excludes zero-actual rows and should not be used alone for intermittent
    retail demand. WAPE is reported as undefined when total actual demand is 0.
    """
    merged = forecasts.merge(
        actual[["product_id", "ds", "demand"]],
        on=["product_id", "ds"],
        how="left",
        suffixes=("", "_actual"),
    ).dropna(subset=["demand", "forecast"])
    if merged.empty:
        raise ValueError("No overlapping forecast and actual observations to evaluate.")

    merged["ae"] = (merged["forecast"] - merged["demand"]).abs()
    merged["se"] = (merged["forecast"] - merged["demand"]) ** 2
    nonzero_actual = merged["demand"].abs() > 0
    merged["ape"] = np.where(nonzero_actual, merged["ae"] / merged["demand"].abs(), np.nan)
    denominator = merged["forecast"].abs() + merged["demand"].abs()
    merged["smape_component"] = np.where(
        denominator > 0,
        200.0 * merged["ae"] / denominator,
        np.nan,
    )

    def summarize(group: pd.DataFrame) -> pd.Series:
        actual_total = float(group["demand"].abs().sum())
        return pd.Series({
            "mae": float(group["ae"].mean()),
            "rmse": float(np.sqrt(group["se"].mean())),
            "mape_pct_nonzero_only": float(group["ape"].mean() * 100) if group["ape"].notna().any() else np.nan,
            "wape_pct": float(group["ae"].sum() / actual_total * 100) if actual_total > 0 else np.nan,
            "smape_pct": float(group["smape_component"].mean()) if group["smape_component"].notna().any() else np.nan,
            "actual_units": actual_total,
            "observations": int(len(group)),
            "zero_actual_observations": int((group["demand"] == 0).sum()),
        })

    per_product = (
        merged.groupby(["product_id", "model"], sort=True)
        .apply(summarize, include_groups=False)
        .reset_index()
    )
    overall = (
        merged.groupby("model", sort=True)
        .apply(summarize, include_groups=False)
        .reset_index()
    )
    overall["product_id"] = "ALL"
    return pd.concat([per_product, overall], ignore_index=True)

# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Load data
    df = load_data()
    # Split for evaluation (chronological)
    train_df, test_df, cutoff = chronological_split(df, test_days=30)

    horizon = 7

    # 1. Validation forecasts: train only on the pre-cutoff history and
    # evaluate against the first `horizon` days in the held-out period.
    validation_naive = naive_forecast(train_df, horizon)
    validation_ma = moving_average_forecast(train_df, horizon)
    validation_lr = linear_regression_forecast(train_df, test_df, horizon)
    validation_forecasts = pd.concat(
        [validation_naive, validation_ma, validation_lr],
        ignore_index=True,
    )

    eval_actual = test_df[test_df["ds"] <= cutoff + pd.Timedelta(days=horizon)]
    errors = compute_errors(validation_forecasts, eval_actual)

    # 2. Production forecasts: refit each model on ALL observations available
    # through the forecast origin, then predict the next 7 calendar days.
    # For this dataset, the forecast origin is 2016-04-24 and the output window
    # is 2016-04-25 through 2016-05-01 (the synthetic campaign window).
    production_naive = naive_forecast(df, horizon)
    production_ma = moving_average_forecast(df, horizon)
    production_lr = linear_regression_forecast(df, df, horizon)
    forecasts = pd.concat(
        [production_naive, production_ma, production_lr],
        ignore_index=True,
    )

    # Save production forecasts, not validation-window predictions.
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "forecast")
    os.makedirs(out_dir, exist_ok=True)
    forecasts_path = os.path.join(out_dir, "forecast_horizon_7d.csv")
    forecasts.to_csv(forecasts_path, index=False)
    print(f"[INFO] Forecasts saved to {forecasts_path}")

    # Save error report (markdown)
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "docs", "forecasting_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Forecast Model Comparison Report\n\n")
        f.write(f"**Chronological validation split:** training up to {cutoff.date()}, test = next 30 days. Horizon = {horizon} days.\n\n")
        f.write(f"**Production forecast window:** {forecasts['ds'].min().date()} to {forecasts['ds'].max().date()}, generated from all available history through {df['ds'].max().date()}.\n\n")
        f.write("## Error metrics (MAE, RMSE, WAPE, sMAPE, diagnostic MAPE)\n\n")
        f.write(errors.to_markdown(index=False))
        f.write("\n\n")
        f.write("### Notes\n")
        f.write("* MAE – Mean Absolute Error (units of demand).\n")
        f.write("* WAPE – weighted absolute percentage error; preferred over MAPE for aggregate retail demand.\n")
        f.write("* sMAPE – symmetric mean absolute percentage error.\n")
        f.write("* MAPE – diagnostic only; excludes zero-actual observations and must not be used alone for intermittent demand.\n")
        f.write("* Linear‑Regression uses all lag / rolling features generated in the M5 feature set.\n")
    print(f"[INFO] Model comparison report written to {report_path}")

