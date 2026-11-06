"""
Day 2: M5 Feature Engineering & Processed Time-Series Pipeline
Strictly adheres to Essential Engineering Rules:
- Rule 1: Documented forecast horizon (7-day horizon: 2016-04-25 to 2016-05-01, d_1914 to d_1920)
- Rule 5: Avoid Future Information Leakage (lags and rolling windows must be offset by >= 7 days)
- Time-aware chronological validation design

Outputs:
- data/processed/m5_processed_features.csv (and .parquet if available)
- data/processed/product_summary_statistics.csv
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import datetime


def add_lagged_rolling_features(df_sales: pd.DataFrame) -> pd.DataFrame:
    """Add horizon-safe lag/rolling features without crossing product groups."""
    df_sales = df_sales.sort_values(["product_id", "date"]).copy()
    grouped = df_sales.groupby("product_id")["sales_units"]
    for lag in (7, 14, 21, 28):
        df_sales[f"lag_{lag}"] = grouped.shift(lag)
    df_sales["rolling_mean_7"] = grouped.transform(
        lambda values: values.shift(7).rolling(7, min_periods=7).mean()
    ).round(2)
    df_sales["rolling_std_7"] = grouped.transform(
        lambda values: values.shift(7).rolling(7, min_periods=7).std()
    ).fillna(0).round(2)
    df_sales["rolling_mean_28"] = grouped.transform(
        lambda values: values.shift(7).rolling(28, min_periods=28).mean()
    ).round(2)
    df_sales["rolling_std_28"] = grouped.transform(
        lambda values: values.shift(7).rolling(28, min_periods=28).std()
    ).fillna(0).round(2)
    df_sales["rolling_min_28"] = grouped.transform(
        lambda values: values.shift(7).rolling(28, min_periods=28).min()
    ).fillna(0)
    df_sales["rolling_max_28"] = grouped.transform(
        lambda values: values.shift(7).rolling(28, min_periods=28).max()
    ).fillna(0)
    price_grouped = df_sales.groupby("product_id")["sell_price"]
    df_sales["price_lag_7"] = price_grouped.shift(7)
    df_sales["price_diff_7"] = (
        df_sales["sell_price"] - df_sales["price_lag_7"]
    ).fillna(0.0).round(2)
    return df_sales

def run_day2_pipeline():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_m5_dir = os.path.join(base_dir, "data", "raw", "m5")
    clean_db_dir = os.path.join(base_dir, "data", "processed", "clean_db_ready")
    processed_dir = os.path.join(base_dir, "data", "processed")
    docs_dir = os.path.join(base_dir, "docs")
    notebooks_dir = os.path.join(base_dir, "notebooks")
    
    os.makedirs(processed_dir, exist_ok=True)
    os.makedirs(docs_dir, exist_ok=True)
    os.makedirs(notebooks_dir, exist_ok=True)

    print("====================================================================")
    print("DAY 2 PIPELINE: Time-Series Feature Engineering & Quality Validation")
    print("====================================================================")

    # 1. Load clean daily sales for the 500 benchmark items (365 historical days)
    sales_file = os.path.join(clean_db_dir, "fct_daily_sales.csv")
    print(f"Loading base historical sales from {sales_file}...")
    df_sales = pd.read_csv(sales_file, keep_default_na=False)
    df_sales["date"] = pd.to_datetime(df_sales["date"])
    df_sales = df_sales.sort_values(["product_id", "date"]).reset_index(drop=True)

    print(f"Loaded {len(df_sales):,} daily sales observations across {df_sales['product_id'].nunique()} products.")
    print(f"Date range: {df_sales['date'].min().strftime('%Y-%m-%d')} to {df_sales['date'].max().strftime('%Y-%m-%d')}")

    # 2. Time-Based Feature Engineering
    print("\n[1/4] Generating calendar and cyclical time features...")
    df_sales["day_of_week"] = df_sales["date"].dt.dayofweek # 0=Monday, 6=Sunday
    df_sales["day_of_month"] = df_sales["date"].dt.day
    df_sales["week_of_year"] = df_sales["date"].dt.isocalendar().week.astype(int)
    df_sales["is_month_start"] = df_sales["date"].dt.is_month_start.astype(int)
    df_sales["is_month_end"] = df_sales["date"].dt.is_month_end.astype(int)
    
    # Cyclical day of week encoding (sin / cos)
    df_sales["dow_sin"] = np.sin(2 * np.pi * df_sales["day_of_week"] / 7).round(4)
    df_sales["dow_cos"] = np.cos(2 * np.pi * df_sales["day_of_week"] / 7).round(4)
    
    # Cyclical month encoding (sin / cos)
    df_sales["month_sin"] = np.sin(2 * np.pi * df_sales["month"] / 12).round(4)
    df_sales["month_cos"] = np.cos(2 * np.pi * df_sales["month"] / 12).round(4)

    # 3. Lag and Rolling Window Features (RULE 5: STRICTLY LEAK-FREE!)
    # Forecast horizon is 7 days (H=7).
    # To forecast Day t+1 through Day t+7 from origin t, any feature must use lags >= 7!
    print("\n[2/4] Generating non-leaking lagged and rolling statistics (lag >= 7)...")
    
    df_sales = add_lagged_rolling_features(df_sales)

    # 4. Product-Level Summary Statistics
    print("\n[3/4] Computing product-level summary statistics...")
    summary_list = []
    for pid, group in df_sales.groupby("product_id"):
        sales = group["sales_units"]
        total_days = len(sales)
        zero_days = (sales == 0).sum()
        zero_pct = round(float(zero_days / total_days * 100), 2)
        mean_sales = round(float(sales.mean()), 2)
        std_sales = round(float(sales.std()), 2)
        cv = round(float(std_sales / mean_sales), 2) if mean_sales > 0 else 0.0
        max_sales = int(sales.max())
        total_units = int(sales.sum())
        cat_id = pid.split("_")[0]
        dept_id = pid.rsplit("_", 1)[0]
        
        # Intermittency classification (ADI / CV squared)
        # Non-zero demands
        non_zero_indices = np.where(sales.values > 0)[0]
        if len(non_zero_indices) > 1:
            intervals = np.diff(non_zero_indices)
            adi = round(float(np.mean(intervals)), 2)
        else:
            adi = 99.0
            
        demand_profile = "Smooth"
        if adi > 1.32 and (cv**2) > 0.49:
            demand_profile = "Lumpy"
        elif adi > 1.32:
            demand_profile = "Intermittent"
        elif (cv**2) > 0.49:
            demand_profile = "Erratic"

        summary_list.append({
            "product_id": pid,
            "category": cat_id,
            "department": dept_id,
            "total_days_observed": total_days,
            "total_units_sold": total_units,
            "mean_daily_sales": mean_sales,
            "std_daily_sales": std_sales,
            "coeff_of_variation": cv,
            "zero_sales_days": int(zero_days),
            "zero_sales_pct": zero_pct,
            "max_daily_sales": max_sales,
            "average_demand_interval": adi,
            "demand_profile": demand_profile
        })

    df_summary = pd.DataFrame(summary_list).sort_values("mean_daily_sales", ascending=False)
    summary_path = os.path.join(processed_dir, "product_summary_statistics.csv")
    df_summary.to_csv(summary_path, index=False)
    print(f"-> Saved product summary statistics ({len(df_summary)} products) to {summary_path}")

    # Print distribution breakdown
    print("\nDemand Profile Distribution across 500 benchmark items:")
    print(df_summary["demand_profile"].value_counts().to_string())

    # 5. Drop initial warm-up days where 28-day lag features are NaN
    # Since max lag is 28 + 7 = 35 days, we trim the first 35 days from modeling table
    initial_rows = len(df_sales)
    df_clean_features = df_sales.dropna(subset=["rolling_mean_28"]).copy()
    trimmed_rows = initial_rows - len(df_clean_features)
    print(f"\n[4/4] Trimmed {trimmed_rows:,} warm-up observations to ensure clean lag arrays.")
    print(f"Final modeling dataset shape: {df_clean_features.shape}")

    # Save processed features
    csv_feat_path = os.path.join(processed_dir, "m5_processed_features.csv")
    df_clean_features.to_csv(csv_feat_path, index=False)
    print(f"-> Saved processed features CSV to {csv_feat_path}")
    
    # Save parquet for high performance
    try:
        parquet_path = os.path.join(processed_dir, "m5_processed_features.parquet")
        df_clean_features.to_parquet(parquet_path, index=False)
        print(f"-> Saved high-performance Parquet format to {parquet_path}")
    except Exception as e:
        print(f"Note: Parquet export skipped ({e})")

    print("\nDay 2 feature engineering pipeline completed successfully!")

if __name__ == "__main__":
    run_day2_pipeline()

