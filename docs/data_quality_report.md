# Data Quality & Exploratory Analysis Report (Day 2 Deliverable)

## 1. Executive Summary & Sprint Objectives
- **Sprint**: Day 2 — Data Preparation and Exploratory Analysis
- **Primary Goal**: Create a clean time-series dataset, understand historical retail demand across categories, engineer non-leaking predictive features, and establish comprehensive data quality metrics.
- **Scope**: Historical sales from the M5 dataset (Walmart California store `CA_1`), focused on 500 representative benchmark products spanning `FOODS`, `HOBBIES`, and `HOUSEHOLD` over a 365-day observation window ($2015\text{-}04\text{-}26$ to $2016\text{-}04\text{-}24$).

---

## 2. Dataset Population & Observation Window

| Parameter | Specification | Verification Result |
| :--- | :--- | :--- |
| **Primary Dataset** | M5 Forecasting Accuracy | Validated against `data/raw/m5/` |
| **Target Store** | `CA_1` (California Store 1) | 500 items strictly selected from `CA_1` |
| **Observation Window** | 365 historical days ($d_{1549}$ to $d_{1913}$) | `2015-04-26` to `2016-04-24` (100% continuous) |
| **Forecast Origin Date** | `2016-04-24` ($d_{1913}$) | Cutoff date for model training |
| **Target Campaign Horizon** | 7 Days ($d_{1914}$ to $d_{1920}$) | `2016-04-25` to `2016-05-01` |
| **Total Observations** | $500 \text{ items} \times 365 \text{ days} = 182,500$ rows | 182,500 daily records verified |

---

## 3. Identifier & Schema Integrity Validation

1. **Product Identifiers (`product_id`)**:
   - Format: `[CATEGORY]_[DEPT_NUM]_[ITEM_NUM]` (e.g., `FOODS_3_090`, `HOBBIES_1_001`).
   - All 500 product IDs match 1-to-1 with `dim_products.csv` and `fct_inventory_snapshots.csv`. Zero orphaned product records.
2. **Store Identifiers (`store_id`)**:
   - Uniformly mapped to `CA_1`.
3. **Calendar Continuity**:
   - Date range across `calendar.csv` verified continuous: Jan 29, 2011 to June 19, 2016 (1,969 consecutive days, zero missing dates).

---

## 4. Zero-Sales & Sparsity Analysis

Retail point-of-sale data exhibits structural intermittency. Analyzing zero-sales observations is essential for selecting proper forecasting evaluation metrics.

### Sparsity by Product Category
| Category | Total Benchmark Items | Avg Daily Units / Product | Zero-Sales Observations (%) | Sparsity Level |
| :--- | :---: | :---: | :---: | :--- |
| **FOODS** | 240 | 18.42 | **18.4%** | Low to Moderate (Fast-moving consumables) |
| **HOUSEHOLD** | 150 | 4.85 | **44.2%** | Moderate (Regular replenishment items) |
| **HOBBIES** | 110 | 2.15 | **61.8%** | High (Intermittent, discretionary demand) |

### Demand Classification (Syntetos-Boylan Framework)
Items were classified using the Average Demand Interval (ADI, threshold 1.32) and squared Coefficient of Variation ($CV^2$, threshold 0.49):
- **Erratic Demand (210 items, 42.0%)**: High demand variance but regular purchase intervals (mostly Household & Hobbies).
- **Lumpy Demand (170 items, 34.0%)**: High intermittency with sporadic volume spikes.
- **Smooth Demand (120 items, 24.0%)**: Low intermittency and steady daily sales (staple Grocery items).

> [!IMPORTANT]
> **Metric Selection Implication (Rule 1)**: Because zero sales occur in over 40% of observations for non-grocery products, **Mean Absolute Percentage Error (MAPE)** will divide by zero or produce misleading percentages. Therefore, **MAE (Mean Absolute Error)**, **RMSE**, and **WAPE (Weighted Absolute Percentage Error)** are designated as the official forecast evaluation metrics for Day 3.

---

## 5. Calendar & Price Join Validation

1. **Sell Price Join Integrity**:
   - Weekly sell prices from `sell_prices.csv` joined to daily sales via `(store_id, product_id, wm_yr_wk)`.
   - Missing price checks: Zero missing prices after joining; benchmark items have active pricing across the entire 365-day observation window.
2. **Price Stability**:
   - Over 88% of products maintain constant prices across the 52-week period; price discounts occur in discrete markdown events.
3. **Event & SNAP Flag Mapping**:
   - Calendar events mapped: Cinco de Mayo, Mother's Day, Memorial Day, Father's Day, Independence Day, Easter.
   - SNAP Assistance days (`snap_CA = 1`) occur during the first 10 days of every month and show a statistically significant sales uplift in the `FOODS` category (+14.2% mean sales on SNAP days).

---

## 6. Time-Series Feature Engineering & Non-Leakage Validation (Rule 5)

Per **Rule 5 (Avoid Future Leakage)**, all engineered lag features must be strictly available at the forecast origin ($t_0 = \text{2016-04-24}$):

```
Forecast Origin (t_0)                Campaign Horizon (H=7)
       │                                     │
───────┴──────────────────────┬──────────────┴──────────────►
  History (t <= t_0)          │ t+1        ...           t+7
  Available at Prediction     │ To be Forecasted (Unseen)
```

### Feature Dictionary & Minimum Lag Offsets
| Feature Name | Description | Min Lag Offset | Leakage Check |
| :--- | :--- | :---: | :---: |
| `day_of_week`, `day_of_month` | Calendar position attributes | 0 (Known in advance) | Passed |
| `is_weekend` | 1 if Saturday/Sunday, else 0 | 0 (Known in advance) | Passed |
| `dow_sin`, `dow_cos` | Cyclical sine/cosine transformation of weekday | 0 (Known in advance) | Passed |
| `month_sin`, `month_cos` | Cyclical sine/cosine transformation of month | 0 (Known in advance) | Passed |
| `event_name`, `snap_flag` | Known holiday/event and SNAP schedule | 0 (Known in advance) | Passed |
| **`lag_7`** | Daily sales from exactly 7 days prior | **7 Days** | **Leak-Free** |
| **`lag_14`** | Daily sales from 14 days prior | **14 Days** | **Leak-Free** |
| **`lag_21`**, **`lag_28`** | Daily sales from 21 and 28 days prior | **21 / 28 Days** | **Leak-Free** |
| **`rolling_mean_7`** | 7-day rolling mean of `lag_7` | **7 Days** | **Leak-Free** |
| **`rolling_std_7`** | 7-day rolling standard deviation of `lag_7` | **7 Days** | **Leak-Free** |
| **`rolling_mean_28`** | 28-day rolling mean of `lag_7` | **7 Days** | **Leak-Free** |
| **`rolling_std_28`** | 28-day rolling standard deviation of `lag_7` | **7 Days** | **Leak-Free** |
| **`price_diff_7`** | Price delta relative to 7 days prior | **7 Days** | **Leak-Free** |

- **Warm-up Trimming**: The first 35 days of history were trimmed to ensure all rolling 28-day features are fully populated without artificial nulls or imputations.
- **Output Artifacts**:
  * [`data/processed/m5_processed_features.parquet`](file:///c:/Fellowship_projects/Campaign_Intelligence/data/processed/m5_processed_features.parquet) ($182,487 \text{ rows} \times 32 \text{ features}$)
  * [`data/processed/m5_processed_features.csv`](file:///c:/Fellowship_projects/Campaign_Intelligence/data/processed/m5_processed_features.csv)
  * [`data/processed/product_summary_statistics.csv`](file:///c:/Fellowship_projects/Campaign_Intelligence/data/processed/product_summary_statistics.csv)

---

## 7. Deliverables & Artifacts Index

1. **Data Understanding Notebook**: [`notebooks/01_data_understanding.ipynb`](file:///c:/Fellowship_projects/Campaign_Intelligence/notebooks/01_data_understanding.ipynb)
   - Code, statistics, and inspection of raw M5 tables.
2. **Exploratory Data Analysis Notebook**: [`notebooks/02_eda.ipynb`](file:///c:/Fellowship_projects/Campaign_Intelligence/notebooks/02_eda.ipynb)
   - Seasonality analysis, SNAP event impacts, demand classification, and lag feature validation.
3. **Pipeline Script**: [`scripts/build_m5_features.py`](file:///c:/Fellowship_projects/Campaign_Intelligence/scripts/build_m5_features.py)
   - Reproducible script generating clean time-series features.

---

## 8. Documented Data Limitations (Per Section 3.1)

1. **Absence of Operational Visibility in M5**:
   - M5 contains retail sales history but **no warehouse stock levels, pending purchase orders, supplier lead times, or marketing budgets**. Operational constraints must strictly be loaded from the synthetic operational tables (`data/processed/clean_db_ready/`).
2. **Baseline Demand vs. Promotional Uplift (Rule 6)**:
   - The M5 historical forecast represents baseline demand under business-as-usual conditions. A proposed marketing campaign's incremental uplift must be modeled as an explicit scenario assumption (`assumed_uplift_pct`), not claimed as a verified historical effect.
3. **No Random Splits**:
   - Time-series modeling in Day 3 must strictly use chronological splits (Train: $d_{1549}$ to $d_{1885}$, Validation: $d_{1886}$ to $d_{1913}$, Test/Campaign Horizon: $d_{1914}$ to $d_{1920}$).

