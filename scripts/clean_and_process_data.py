"""
Data Cleaning, Processing, and Validation Pipeline
Prepares all retail demand and operational datasets for Neon PostgreSQL ingestion.

Inputs:
- data/raw/m5/ (calendar.csv, sell_prices.csv, sales_train_validation.csv)
- data/processed/synthetic/ (5 core operational tables)

Outputs (in data/processed/clean_db_ready/):
1. dim_products.csv (500 rows, PK: product_id)
2. fct_daily_sales.csv (~182,500 rows, PK: (product_id, store_id, date))
3. fct_inventory_snapshots.csv (500 rows, PK: (product_id, store_id))
4. fct_supplier_replenishment.csv (500 rows, PK: (supplier_id, product_id))
5. dim_campaigns.csv (50 rows, PK: campaign_id)
6. fct_campaign_cost_assumptions.csv (50 rows, PK: campaign_id)
7. fct_campaign_proposals.csv (50 rows, PK: proposal_id)
8. schema_neon.sql (PostgreSQL DDL script with PKs, FKs, types, and indexes)
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import datetime

def clean_and_process():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_m5_dir = os.path.join(base_dir, "data", "raw", "m5")
    synth_dir = os.path.join(base_dir, "data", "processed", "synthetic")
    out_dir = os.path.join(base_dir, "data", "processed", "clean_db_ready")
    docs_dir = os.path.join(base_dir, "docs")
    
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(docs_dir, exist_ok=True)

    print("==========================================================")
    print("STEP 1: Cleaning & Validating Synthetic Operational Tables")
    print("==========================================================")
    
    # 1. Load synthetic tables
    df_camp = pd.read_csv(os.path.join(synth_dir, "campaigns.csv"))
    df_costs = pd.read_csv(os.path.join(synth_dir, "campaign_cost_assumptions.csv"))
    df_props = pd.read_csv(os.path.join(synth_dir, "campaign_proposals.csv"))
    df_inv = pd.read_csv(os.path.join(synth_dir, "inventory_snapshots.csv"))
    df_supp = pd.read_csv(os.path.join(synth_dir, "supplier_replenishment.csv"))
    
    # Clean dim_campaigns
    print(f"Processing dim_campaigns ({len(df_camp)} rows)...")
    df_camp["campaign_id"] = df_camp["campaign_id"].str.strip()
    df_camp["campaign_name"] = df_camp["campaign_name"].str.strip()
    df_camp["campaign_type"] = df_camp["campaign_type"].str.strip()
    df_camp["start_date"] = pd.to_datetime(df_camp["start_date"]).dt.strftime("%Y-%m-%d")
    df_camp["end_date"] = pd.to_datetime(df_camp["end_date"]).dt.strftime("%Y-%m-%d")
    df_camp["target_segments"] = df_camp["target_segments"].str.strip()
    df_camp["campaign_budget"] = df_camp["campaign_budget"].astype(float).round(2)
    df_camp["discount_rate"] = df_camp["discount_rate"].astype(float).round(4)
    df_camp["status"] = df_camp["status"].str.strip()
    
    # Save dim_campaigns
    camp_clean_path = os.path.join(out_dir, "dim_campaigns.csv")
    df_camp.to_csv(camp_clean_path, index=False)
    print(f"-> Saved clean dim_campaigns to {camp_clean_path}")

    # Clean fct_campaign_cost_assumptions
    print(f"Processing fct_campaign_cost_assumptions ({len(df_costs)} rows)...")
    df_costs["campaign_id"] = df_costs["campaign_id"].str.strip()
    df_costs["fixed_campaign_cost"] = df_costs["fixed_campaign_cost"].astype(float).round(2)
    df_costs["cost_per_contact"] = df_costs["cost_per_contact"].astype(float).round(4)
    df_costs["logistics_cost_assumption"] = df_costs["logistics_cost_assumption"].astype(float).round(2)
    
    # Foreign key integrity check: costs -> campaigns
    missing_camp_in_costs = set(df_costs["campaign_id"]) - set(df_camp["campaign_id"])
    assert len(missing_camp_in_costs) == 0, f"FK Violation: cost assumptions contain unknown campaigns: {missing_camp_in_costs}"
    
    cost_clean_path = os.path.join(out_dir, "fct_campaign_cost_assumptions.csv")
    df_costs.to_csv(cost_clean_path, index=False)
    print(f"-> Saved clean fct_campaign_cost_assumptions to {cost_clean_path}")

    # Clean fct_campaign_proposals
    print(f"Processing fct_campaign_proposals ({len(df_props)} rows)...")
    df_props["proposal_id"] = df_props["proposal_id"].str.strip()
    df_props["campaign_id"] = df_props["campaign_id"].str.strip()
    df_props["forecast_version"] = df_props["forecast_version"].str.strip()
    df_props["decision_status"] = df_props["decision_status"].str.strip()
    df_props["approval_status"] = df_props["approval_status"].str.strip()
    df_props["created_at"] = pd.to_datetime(df_props["created_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    
    # Convert empty or NaN approved_at to explicit None/blank string for SQL NULL
    df_props["approved_at"] = df_props["approved_at"].apply(
        lambda x: pd.to_datetime(x).strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(x) and str(x).strip() != "" else ""
    )
    
    # FK check: proposals -> campaigns
    missing_camp_in_props = set(df_props["campaign_id"]) - set(df_camp["campaign_id"])
    assert len(missing_camp_in_props) == 0, f"FK Violation: proposals contain unknown campaigns: {missing_camp_in_props}"

    prop_clean_path = os.path.join(out_dir, "fct_campaign_proposals.csv")
    df_props.to_csv(prop_clean_path, index=False)
    print(f"-> Saved clean fct_campaign_proposals to {prop_clean_path}")

    # ----------------------------------------------------------
    # STEP 2: Building dim_products and Inventory / Supplier Tables
    # ----------------------------------------------------------
    print("\n==========================================================")
    print("STEP 2: Building dim_products & Cleaning Inventory/Suppliers")
    print("==========================================================")
    
    # Extract unique benchmark products from inventory snapshots
    prod_cols = ["product_id", "product_name", "store_id"]
    df_prod_base = df_inv[prod_cols].drop_duplicates().copy()
    
    # Derive cat_id and dept_id from product_id (e.g. FOODS_3_090 -> cat: FOODS, dept: FOODS_3)
    df_prod_base["cat_id"] = df_prod_base["product_id"].apply(lambda x: x.split("_")[0])
    df_prod_base["dept_id"] = df_prod_base["product_id"].apply(lambda x: x.rsplit("_", 1)[0])
    
    # Get baseline sell price from sell_prices.csv
    print("Loading M5 prices to assign base_price to dim_products...")
    prices_raw = pd.read_csv(os.path.join(raw_m5_dir, "sell_prices.csv"))
    prices_ca1_latest = prices_raw[(prices_raw["store_id"] == "CA_1") & (prices_raw["wm_yr_wk"] == 11613)]
    if prices_ca1_latest.empty:
        max_wk = prices_raw[prices_raw["store_id"] == "CA_1"]["wm_yr_wk"].max()
        prices_ca1_latest = prices_raw[(prices_raw["store_id"] == "CA_1") & (prices_raw["wm_yr_wk"] == max_wk)]
        
    price_map = dict(zip(prices_ca1_latest["item_id"], prices_ca1_latest["sell_price"]))
    df_prod_base["base_price"] = df_prod_base["product_id"].apply(lambda pid: price_map.get(pid, 3.50)).round(2)

    # Reorder columns for dim_products
    dim_products = df_prod_base[["product_id", "product_name", "cat_id", "dept_id", "store_id", "base_price"]].copy()
    dim_prod_path = os.path.join(out_dir, "dim_products.csv")
    dim_products.to_csv(dim_prod_path, index=False)
    print(f"-> Saved dim_products ({len(dim_products)} products) to {dim_prod_path}")

    # Clean fct_inventory_snapshots
    print("Cleaning fct_inventory_snapshots...")
    df_inv["product_id"] = df_inv["product_id"].str.strip()
    df_inv["store_id"] = df_inv["store_id"].str.strip()
    df_inv["on_hand_stock"] = df_inv["on_hand_stock"].astype(int)
    df_inv["reserved_stock"] = df_inv["reserved_stock"].astype(int)
    # Ensure available stock is non-negative and strictly matches on_hand - reserved
    df_inv["available_stock"] = (df_inv["on_hand_stock"] - df_inv["reserved_stock"]).clip(lower=0)
    df_inv["safety_stock"] = df_inv["safety_stock"].astype(int).clip(lower=0)
    df_inv["inventory_updated_at"] = pd.to_datetime(df_inv["inventory_updated_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    
    # Save clean inventory table (FK to dim_products)
    inv_clean_cols = ["product_id", "product_name", "store_id", "on_hand_stock", "reserved_stock", "available_stock", "safety_stock", "inventory_updated_at"]
    df_inv = df_inv[inv_clean_cols]
    inv_clean_path = os.path.join(out_dir, "fct_inventory_snapshots.csv")
    df_inv.to_csv(inv_clean_path, index=False)
    print(f"-> Saved clean fct_inventory_snapshots ({len(df_inv)} rows) to {inv_clean_path}")

    # Clean fct_supplier_replenishment
    print("Cleaning fct_supplier_replenishment...")
    df_supp["supplier_id"] = df_supp["supplier_id"].str.strip()
    df_supp["product_id"] = df_supp["product_id"].str.strip()
    df_supp["product_name"] = df_supp["product_name"].str.strip()
    # In SQL, unknown lead time is represented as NULL, not -1
    df_supp["lead_time_days"] = df_supp["lead_time_days"].apply(lambda x: "" if x == -1 or pd.isnull(x) else int(x))
    df_supp["minimum_order_quantity"] = df_supp["minimum_order_quantity"].astype(int)
    df_supp["replenishment_capacity"] = df_supp["replenishment_capacity"].astype(int)
    df_supp["expected_replenishment_date"] = pd.to_datetime(df_supp["expected_replenishment_date"]).dt.strftime("%Y-%m-%d")
    df_supp["supplier_status"] = df_supp["supplier_status"].str.strip()

    supp_clean_cols = ["supplier_id", "product_id", "product_name", "lead_time_days", "minimum_order_quantity", "replenishment_capacity", "expected_replenishment_date", "supplier_status"]
    df_supp = df_supp[supp_clean_cols]
    supp_clean_path = os.path.join(out_dir, "fct_supplier_replenishment.csv")
    df_supp.to_csv(supp_clean_path, index=False)
    print(f"-> Saved clean fct_supplier_replenishment ({len(df_supp)} rows) to {supp_clean_path}")

    # ----------------------------------------------------------
    # STEP 3: M5 Demand Time-Series Unpivoting & Feature Enrichment
    # ----------------------------------------------------------
    print("\n==========================================================")
    print("STEP 3: Processing M5 Daily Historical Sales (Past 365 Days)")
    print("==========================================================")
    
    # 365 historical days: d_1549 (2015-04-26) to d_1913 (2016-04-24)
    target_d_cols = [f"d_{i}" for i in range(1549, 1914)]
    print(f"Filtering sales_train_validation.csv for the 500 benchmark items across {len(target_d_cols)} days...")
    
    target_pids = set(dim_products["product_id"])
    sales_cols = ["id", "item_id", "dept_id", "cat_id", "store_id"] + target_d_cols
    sales_raw = pd.read_csv(os.path.join(raw_m5_dir, "sales_train_validation.csv"), usecols=sales_cols)
    sales_benchmark = sales_raw[(sales_raw["store_id"] == "CA_1") & (sales_raw["item_id"].isin(target_pids))].copy()
    
    print(f"Melted benchmark dataset shape: {sales_benchmark.shape}")
    
    # Unpivot wide table to long time-series format
    df_melted = pd.melt(
        sales_benchmark,
        id_vars=["item_id", "store_id"],
        value_vars=target_d_cols,
        var_name="d",
        value_name="sales_units"
    )
    df_melted.rename(columns={"item_id": "product_id"}, inplace=True)
    df_melted["sales_units"] = df_melted["sales_units"].astype(int)
    print(f"Long format time-series created: {len(df_melted):,} rows.")

    # Load Calendar metadata for enrichment
    print("Joining calendar metadata (date, weekday, month, event, snap)...")
    cal = pd.read_csv(os.path.join(raw_m5_dir, "calendar.csv"))
    cal_subset = cal[["d", "date", "wm_yr_wk", "weekday", "wday", "month", "year", "event_name_1", "snap_CA"]].copy()
    cal_subset["event_name_1"] = cal_subset["event_name_1"].fillna("None")
    cal_subset["is_weekend"] = cal_subset["wday"].apply(lambda x: 1 if x in [1, 2] else 0) # wday 1=Saturday, 2=Sunday in M5
    
    # Merge melted sales with calendar
    df_sales_enriched = df_melted.merge(cal_subset, on="d", how="left")
    
    # Join sell prices on (store_id, item_id, wm_yr_wk)
    print("Joining weekly sell prices...")
    prices_ca1 = prices_raw[prices_raw["store_id"] == "CA_1"][["item_id", "wm_yr_wk", "sell_price"]].rename(columns={"item_id": "product_id"})
    df_sales_enriched = df_sales_enriched.merge(prices_ca1, on=["product_id", "wm_yr_wk"], how="left")
    
    # Fill any missing prices with the item's baseline price from dim_products
    prod_price_map = dict(zip(dim_products["product_id"], dim_products["base_price"]))
    df_sales_enriched["sell_price"] = df_sales_enriched["sell_price"].fillna(
        df_sales_enriched["product_id"].map(prod_price_map)
    ).round(2)
    
    # Clean final column structure
    fct_daily_sales = df_sales_enriched[[
        "product_id",
        "store_id",
        "date",
        "sales_units",
        "sell_price",
        "weekday",
        "month",
        "year",
        "is_weekend",
        "event_name_1",
        "snap_CA"
    ]].rename(columns={
        "event_name_1": "event_name",
        "snap_CA": "snap_flag"
    }).copy()
    
    # Fill event_name with 'None' for non-event days
    fct_daily_sales["event_name"] = fct_daily_sales["event_name"].fillna("None")
    
    # Sort chronologically by product_id and date
    fct_daily_sales = fct_daily_sales.sort_values(["product_id", "date"]).reset_index(drop=True)
    
    sales_clean_path = os.path.join(out_dir, "fct_daily_sales.csv")
    fct_daily_sales.to_csv(sales_clean_path, index=False)
    print(f"-> Saved clean fct_daily_sales ({len(fct_daily_sales):,} rows) to {sales_clean_path}")

    # ----------------------------------------------------------
    # STEP 4: Generate PostgreSQL Schema DDL Script (schema_neon.sql)
    # ----------------------------------------------------------
    print("\n==========================================================")
    print("STEP 4: Generating PostgreSQL DDL for Neon DB Ingestion")
    print("==========================================================")
    
    ddl_sql = """-- ==============================================================
-- Neon PostgreSQL Database Schema for Campaign Intelligence System
-- Generated for Automated Clean Ingestion
-- ==============================================================

-- 1. Dimension: Products
CREATE TABLE IF NOT EXISTS dim_products (
    product_id VARCHAR(50) PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    cat_id VARCHAR(50) NOT NULL,
    dept_id VARCHAR(50) NOT NULL,
    store_id VARCHAR(20) NOT NULL,
    base_price NUMERIC(10, 2) NOT NULL CHECK (base_price > 0)
);

-- 2. Fact: Historical Daily Sales Time-Series
CREATE TABLE IF NOT EXISTS fct_daily_sales (
    product_id VARCHAR(50) NOT NULL REFERENCES dim_products(product_id) ON DELETE CASCADE,
    store_id VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    sales_units INTEGER NOT NULL CHECK (sales_units >= 0),
    sell_price NUMERIC(10, 2) NOT NULL CHECK (sell_price > 0),
    weekday VARCHAR(20) NOT NULL,
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    year INTEGER NOT NULL,
    is_weekend INTEGER NOT NULL CHECK (is_weekend IN (0, 1)),
    event_name VARCHAR(100) DEFAULT 'None',
    snap_flag INTEGER NOT NULL CHECK (snap_flag IN (0, 1)),
    PRIMARY KEY (product_id, store_id, date)
);
CREATE INDEX IF NOT EXISTS idx_daily_sales_product_date ON fct_daily_sales(product_id, date);
CREATE INDEX IF NOT EXISTS idx_daily_sales_date ON fct_daily_sales(date);

-- 3. Fact: Inventory Snapshots
CREATE TABLE IF NOT EXISTS fct_inventory_snapshots (
    product_id VARCHAR(50) NOT NULL REFERENCES dim_products(product_id) ON DELETE CASCADE,
    product_name VARCHAR(255) NOT NULL,
    store_id VARCHAR(20) NOT NULL,
    on_hand_stock INTEGER NOT NULL CHECK (on_hand_stock >= 0),
    reserved_stock INTEGER NOT NULL CHECK (reserved_stock >= 0),
    available_stock INTEGER NOT NULL CHECK (available_stock >= 0),
    safety_stock INTEGER NOT NULL CHECK (safety_stock >= 0),
    inventory_updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (product_id, store_id)
);

-- 4. Fact: Supplier Replenishment
CREATE TABLE IF NOT EXISTS fct_supplier_replenishment (
    supplier_id VARCHAR(50) NOT NULL,
    product_id VARCHAR(50) NOT NULL REFERENCES dim_products(product_id) ON DELETE CASCADE,
    product_name VARCHAR(255) NOT NULL,
    lead_time_days INTEGER CHECK (lead_time_days IS NULL OR lead_time_days >= 0),
    minimum_order_quantity INTEGER NOT NULL CHECK (minimum_order_quantity > 0),
    replenishment_capacity INTEGER NOT NULL CHECK (replenishment_capacity > 0),
    expected_replenishment_date DATE NOT NULL,
    supplier_status VARCHAR(50) NOT NULL CHECK (supplier_status IN ('active', 'suspended')),
    PRIMARY KEY (supplier_id, product_id)
);

-- 5. Dimension: Campaigns
CREATE TABLE IF NOT EXISTS dim_campaigns (
    campaign_id VARCHAR(50) PRIMARY KEY,
    campaign_name VARCHAR(255) NOT NULL,
    campaign_type VARCHAR(100) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL CHECK (end_date >= start_date),
    target_product_ids VARCHAR(255) NOT NULL,
    target_product_names VARCHAR(500) NOT NULL,
    target_segments VARCHAR(100) NOT NULL,
    campaign_budget NUMERIC(12, 2) NOT NULL CHECK (campaign_budget > 0),
    discount_rate NUMERIC(5, 4) NOT NULL CHECK (discount_rate BETWEEN 0 AND 1),
    status VARCHAR(50) NOT NULL DEFAULT 'candidate',
    scenario_label VARCHAR(255) NOT NULL
);

-- 6. Fact: Campaign Cost Assumptions
CREATE TABLE IF NOT EXISTS fct_campaign_cost_assumptions (
    campaign_id VARCHAR(50) PRIMARY KEY REFERENCES dim_campaigns(campaign_id) ON DELETE CASCADE,
    fixed_campaign_cost NUMERIC(10, 2) NOT NULL CHECK (fixed_campaign_cost >= 0),
    cost_per_contact NUMERIC(10, 4) NOT NULL CHECK (cost_per_contact >= 0),
    discount_cost_assumption VARCHAR(100) NOT NULL,
    logistics_cost_assumption NUMERIC(10, 2) NOT NULL CHECK (logistics_cost_assumption >= 0),
    cost_accounting_method VARCHAR(100) NOT NULL
);

-- 7. Fact: Campaign Proposals & Audit Log
CREATE TABLE IF NOT EXISTS fct_campaign_proposals (
    proposal_id VARCHAR(50) PRIMARY KEY,
    campaign_id VARCHAR(50) NOT NULL REFERENCES dim_campaigns(campaign_id) ON DELETE CASCADE,
    forecast_version VARCHAR(100) NOT NULL,
    decision_status VARCHAR(100) NOT NULL,
    selected_option_id VARCHAR(100) NOT NULL,
    budget_validation_status VARCHAR(100) NOT NULL,
    inventory_validation_status VARCHAR(100) NOT NULL,
    approval_status VARCHAR(50) NOT NULL CHECK (approval_status IN ('approved', 'pending_review', 'rejected')),
    approver_id VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    approved_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_proposals_campaign_id ON fct_campaign_proposals(campaign_id);
"""
    sql_path = os.path.join(out_dir, "schema_neon.sql")
    with open(sql_path, "w", encoding="utf-8") as f:
        f.write(ddl_sql)
    print(f"-> Saved Neon PostgreSQL schema DDL to {sql_path}")

    print("\nAll data cleaning, transformation, and validation steps completed successfully!")

if __name__ == "__main__":
    clean_and_process()
