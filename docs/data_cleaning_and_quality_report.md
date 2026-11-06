# Data Cleaning, Transformation, and Quality Assurance Report

## 1. Executive Summary
This document details the cleaning, processing, normalization, and quality validation performed on all raw retail demand data (M5 Forecasting) and synthetic operational datasets.

All resulting tables have been structured, typed, and saved under:
```
data/processed/clean_db_ready/
```
These tables are ready for immediate ingestion into **Neon PostgreSQL** via the provided DDL script [`schema_neon.sql`](file:///c:/Fellowship_projects/Campaign_Intelligence/data/processed/clean_db_ready/schema_neon.sql).

---

## 2. Processed Database Schema & Table Summary

| Table Name | File Name | Row Count | Primary Key | Foreign Keys | Purpose |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `dim_products` | `dim_products.csv` | **500** | `product_id` | — | Product master catalog across FOODS, HOBBIES, and HOUSEHOLD with base prices. |
| `dim_campaigns` | `dim_campaigns.csv` | **50** | `campaign_id` | — | Promotional campaign registry (strictly 1 segment/row, $\le 2$ products/row). |
| `fct_daily_sales` | `fct_daily_sales.csv` | **182,500** | `(product_id, store_id, date)` | `dim_products(product_id)` | 365-day unpivoted historical demand time-series enriched with calendar events and prices. |
| `fct_inventory_snapshots`| `fct_inventory_snapshots.csv` | **500** | `(product_id, store_id)` | `dim_products(product_id)` | Point-in-time on-hand, reserved, available, and safety stock positions. |
| `fct_supplier_replenishment`| `fct_supplier_replenishment.csv`| **500** | `(supplier_id, product_id)` | `dim_products(product_id)` | Procurement lead times, MOQs, capacity, arrival dates, and vendor statuses. |
| `fct_campaign_cost_assumptions`| `fct_campaign_cost_assumptions.csv`| **50** | `campaign_id` | `dim_campaigns(campaign_id)` | Fixed, variable contact, discount subsidy, and logistics costs per campaign. |
| `fct_campaign_proposals` | `fct_campaign_proposals.csv` | **50** | `proposal_id` | `dim_campaigns(campaign_id)` | State machine proposal records (budget checks, inventory checks, approval audit logs). |

---

## 3. Data Cleaning & Transformation Pipeline

### 3.1 M5 Time-Series Unpivoting & Feature Enrichment (`fct_daily_sales.csv`)
1. **Wide-to-Long Normalization**:
   - The raw M5 dataset (`sales_train_validation.csv`) stored daily sales horizontally in 1,913 columns (`d_1` to `d_1913`). Storing 1,900+ columns in PostgreSQL is an anti-pattern.
   - Unpivoted the 500 benchmark items over the trailing **365 days** ($d_{1549}$ to $d_{1913}$, from `2015-04-26` to `2016-04-24`) into a clean long format ($500 \times 365 = 182,500$ rows).
2. **Calendar Metadata Joining**:
   - Joined `calendar.csv` on day code (`d`) to inject actual Gregorian `date`, `weekday`, `month`, `year`, `is_weekend` (derived from Saturday/Sunday indicators), and `event_name` (holidays, sporting events).
   - Filled non-event days with `'None'` to ensure standard string filtering in SQL queries.
3. **Weekly Price Alignment**:
   - Joined `sell_prices.csv` using the composite key `(store_id, product_id, wm_yr_wk)` to associate the exact historical price on each day.
   - Cleaned fallback values: missing prices were populated with the product's baseline price from `dim_products`.

### 3.2 Product Master Catalog (`dim_products.csv`)
1. **Catalog Extraction**:
   - Derived unique product identifiers from the 500 benchmark items in store `CA_1`.
2. **Category & Department Derivation**:
   - Extracted `cat_id` (e.g. `FOODS`, `HOBBIES`, `HOUSEHOLD`) and `dept_id` (e.g. `FOODS_1`, `HOBBIES_1`) from standard M5 naming conventions.
3. **Product Name Normalization**:
   - Mapped all product IDs to consistent, human-readable retail product titles (e.g. `Deluxe Acrylic Craft Paint Set (#1)`).
4. **Base Pricing**:
   - Mapped prices from `sell_prices.csv` around origin week `11613`, ensuring every item has a validated positive base price.

### 3.3 Inventory Position Standardization (`fct_inventory_snapshots.csv`)
1. **Non-Negative Stock Constraints**:
   - Checked that `on_hand_stock >= 0`, `reserved_stock >= 0`, `available_stock >= 0`, and `safety_stock >= 0`.
2. **Stock Balance Verification**:
   - Enforced the invariant $\text{available\_stock} = \max(0, \text{on\_hand\_stock} - \text{reserved\_stock})$.
3. **Timestamp Formatting**:
   - Standardized `inventory_updated_at` to standard ISO-8601 (`YYYY-MM-DD HH:MM:SS`).

### 3.4 Procurement & Lead Time Cleaning (`fct_supplier_replenishment.csv`)
1. **SQL Null Handling for Lead Times**:
   - Replaced dummy negative indicators (`-1`) with standard SQL `NULL` for items with unknown or suspended lead times (e.g., `HOBBIES_1_214`).
2. **Status Normalization**:
   - Enforced strict enum values for `supplier_status` (`active` or `suspended`).
3. **Date Validation**:
   - Standardized `expected_replenishment_date` to `YYYY-MM-DD`.

### 3.5 Campaign Catalogue & Cost Modeling (`dim_campaigns.csv` & `fct_campaign_cost_assumptions.csv`)
1. **Single Segment Enforcement**:
   - Verified that `target_segments` contains strictly one audience segment per row (no comma-delimited strings).
2. **Product Count Enforcement**:
   - Verified that `target_product_ids` contains at most 2 product IDs per campaign.
3. **Date Consistency**:
   - Verified that `start_date <= end_date` (all 7-day windows: `2016-04-25` to `2016-05-01`).
4. **Cost Accounting Alignment**:
   - Matched all 50 campaign IDs 1-to-1 with cost assumptions, verifying non-negative fixed costs, unit contact costs, and logistics surcharges.

### 3.6 Proposals & Governance Audit Trail (`fct_campaign_proposals.csv`)
1. **Lifecycle States**:
   - Validated `decision_status` (`ranked_feasible`, `rejected_by_policy`) and `approval_status` (`approved`, `pending_review`, `rejected`).
2. **Audit Timestamp Cleaning**:
   - Converted empty approved timestamps on pending proposals to SQL `NULL` values.

---

## 4. Referential Integrity (Foreign Key Verification)

The pipeline executed automated referential integrity checks:
- $\checkmark$ **`dim_campaigns` $\to$ `fct_campaign_cost_assumptions`**: 0 orphaned records (50/50 matched).
- $\checkmark$ **`dim_campaigns` $\to$ `fct_campaign_proposals`**: 0 orphaned records (50/50 matched).
- $\checkmark$ **`dim_products` $\to$ `fct_inventory_snapshots`**: 0 orphaned records (500/500 matched).
- $\checkmark$ **`dim_products` $\to$ `fct_supplier_replenishment`**: 0 orphaned records (500/500 matched).
- $\checkmark$ **`dim_products` $\to$ `fct_daily_sales`**: 0 orphaned records (182,500/182,500 matched).

---

## 5. Automated Pipeline Script

The complete reproducible cleaning and validation logic is available at:
[`scripts/clean_and_process_data.py`](file:///c:/Fellowship_projects/Campaign_Intelligence/scripts/clean_and_process_data.py)

To re-run the entire pipeline:
```bash
python scripts/clean_and_process_data.py
```
Outputs are written deterministically to `data/processed/clean_db_ready/`.

