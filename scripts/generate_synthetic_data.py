"""
Synthetic Data Generator for Campaign Intelligence
Strictly aligned with Section 3.5 of the Project Specification.

Generates the 5 required synthetic operational tables:
1. campaigns.csv (50 rows)
   * target_segments has strictly 1 segment per row
   * target_product_ids has at most 2 product IDs
   * contains human-readable target_product_names
2. campaign_cost_assumptions.csv (50 rows, 1-to-1 match with campaigns)
3. campaign_proposals.csv (50 rows, 1-to-1 proposal lifecycle audit trail)
4. inventory_snapshots.csv (500 rows, includes product_name)
5. supplier_replenishment.csv (500 rows, includes product_name)
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

def build_product_name(item_id, cat_id, dept_id):
    tokens = item_id.split("_")
    item_num = int(tokens[-1]) if len(tokens) >= 3 and tokens[-1].isdigit() else 1
    
    foods_adjectives = ["Organic", "Farm Fresh", "Whole Grain", "Artisan", "Golden", "Crispy", "Homestyle", "Premium", "Sweet & Savory", "Deluxe"]
    foods_nouns = ["Granola Cereal", "Cheddar Cheese Block", "Pasta Sauce", "Sparkling Water 6-Pack", "Greek Yogurt Cup", 
                   "Almond Butter Jar", "Multi-Grain Bread", "Organic Cold Brew Coffee", "Sea Salt Crackers", "Pure Maple Syrup"]
    
    hobbies_adjectives = ["Classic", "Deluxe", "Beginner's", "Heavy Duty", "Pro Studio", "Eco-Friendly", "All-Weather", "Vintage", "Pocket", "Master"]
    hobbies_nouns = ["Acrylic Craft Paint Set", "Wood Carving Kit", "Precision Model Glue", "Ceramic Sculpting Clay", "Sketching Pad & Pencils",
                     "Embroidery Needle Set", "Miniature Board Game", "Canvas Painting Panel", "Calligraphy Ink Pen", "Puzzle Board 1000pc"]
    
    household_adjectives = ["Ultra Clean", "Heavy Duty", "Gentle Care", "Lavender Scented", "Microfiber", "Multi-Surface", "Compact", "Ergonomic", "Biodegradable", "Stainless"]
    household_nouns = ["Surface Disinfectant Spray", "Laundry Detergent Pods", "Kitchen Paper Towels 12-Pack", "Dishwasher Gel Rinse", "Storage Tote Box 50L",
                       "Dusting Mop Refills", "Trash Bags 30-Gallon", "Non-Stick Frying Pan", "Silicone Baking Mat", "LED Desk Lamp"]
    
    if cat_id == "FOODS":
        adj = foods_adjectives[item_num % len(foods_adjectives)]
        noun = foods_nouns[(item_num // len(foods_adjectives)) % len(foods_nouns)]
        return f"{adj} {noun} (#{item_num})"
    elif cat_id == "HOBBIES":
        adj = hobbies_adjectives[item_num % len(hobbies_adjectives)]
        noun = hobbies_nouns[(item_num // len(hobbies_adjectives)) % len(hobbies_nouns)]
        return f"{adj} {noun} (#{item_num})"
    else:
        adj = household_adjectives[item_num % len(household_adjectives)]
        noun = household_nouns[(item_num // len(household_adjectives)) % len(household_nouns)]
        return f"{adj} {noun} (#{item_num})"

def main():
    np.random.seed(42)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_m5_dir = os.path.join(base_dir, "data", "raw", "m5")
    out_dir = os.path.join(base_dir, "data", "processed", "synthetic")
    docs_dir = os.path.join(base_dir, "docs")
    
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(docs_dir, exist_ok=True)

    print(f"Loading M5 raw data from {raw_m5_dir}...")
    
    campaign_start = "2016-04-25"
    campaign_end = "2016-05-01"
    snapshot_time = "2016-04-24 23:59:00"

    # 1. Select 500 benchmark products from CA_1 store
    sales_path = os.path.join(raw_m5_dir, "sales_train_validation.csv")
    usecols = ["id", "item_id", "dept_id", "cat_id", "store_id"] + [f"d_{i}" for i in range(1884, 1914)]
    print("Reading M5 sales for CA_1 benchmark selection (500 products)...")
    sales_df = pd.read_csv(sales_path, usecols=usecols)
    sales_ca1 = sales_df[sales_df["store_id"] == "CA_1"].copy()

    # Calculate 30-day demand statistics
    hist_cols = [f"d_{i}" for i in range(1884, 1914)]
    sales_ca1["mean_daily_sales"] = sales_ca1[hist_cols].mean(axis=1)
    sales_ca1["std_daily_sales"] = sales_ca1[hist_cols].std(axis=1).fillna(0.5)

    # Mandatory anchor items for benchmark scenario testing
    mandatory_items = [
        "HOBBIES_1_001", "HOBBIES_1_002", "FOODS_3_586", "FOODS_3_090",
        "HOBBIES_1_004", "FOODS_3_252", "HOUSEHOLD_1_032", "HOUSEHOLD_1_118",
        "FOODS_2_197", "HOUSEHOLD_2_041", "HOBBIES_1_214"
    ]
    mandatory_sub = sales_ca1[sales_ca1["item_id"].isin(mandatory_items)]
    remaining_ca1 = sales_ca1[~sales_ca1["item_id"].isin(mandatory_items)]

    # Select remaining items to reach exactly 500 products
    needed_count = 500 - len(mandatory_sub)
    prod_alloc = [("FOODS", 240), ("HOUSEHOLD", 150), ("HOBBIES", needed_count - 390)]
    selected_items = [mandatory_sub]
    for cat, count in prod_alloc:
        sub = remaining_ca1[remaining_ca1["cat_id"] == cat].sort_values("mean_daily_sales", ascending=False).head(count)
        selected_items.append(sub)
    
    bench_500 = pd.concat(selected_items, ignore_index=True)
    bench_500 = bench_500.drop_duplicates(subset=["item_id"]).head(500)
    print(f"Selected {len(bench_500)} products from M5 CA_1.")

    # 2. Join with sell prices
    prices_path = os.path.join(raw_m5_dir, "sell_prices.csv")
    prices_df = pd.read_csv(prices_path)
    prices_ca1 = prices_df[(prices_df["store_id"] == "CA_1") & (prices_df["wm_yr_wk"] == 11613)]
    if prices_ca1.empty:
        latest_wk = prices_df[prices_df["store_id"] == "CA_1"]["wm_yr_wk"].max()
        prices_ca1 = prices_df[(prices_df["store_id"] == "CA_1") & (prices_df["wm_yr_wk"] == latest_wk)]
        
    bench_500 = bench_500.merge(prices_ca1[["item_id", "sell_price"]], on="item_id", how="left")
    bench_500["sell_price"] = bench_500["sell_price"].fillna(4.25).round(2)
    bench_500["product_id"] = bench_500["item_id"]
    
    # Generate human-readable product names
    bench_500["product_name"] = bench_500.apply(
        lambda r: build_product_name(r["item_id"], r["cat_id"], r["dept_id"]), axis=1
    )
    product_map = dict(zip(bench_500["product_id"], bench_500["product_name"]))

    # -------------------------------------------------------------
    # 1. INVENTORY SNAPSHOTS (500 rows)
    # -------------------------------------------------------------
    print("Generating 500 Inventory Snapshots with product_name...")
    inv_records = []
    for idx, row in bench_500.iterrows():
        p_id = row["product_id"]
        p_name = row["product_name"]
        store = "CA_1"
        mean_s = max(row["mean_daily_sales"], 1.0)
        std_s = max(row["std_daily_sales"], 0.5)
        
        safety_stock = int(np.ceil(1.65 * np.sqrt(3) * std_s))
        days_supply = np.random.uniform(12, 18)
        on_hand = int(np.ceil(mean_s * days_supply))
        reserved = int(np.ceil(on_hand * 0.15))
        available = on_hand - reserved
        inv_updated_at = snapshot_time
        
        # Test scenario anchors
        if p_id == "HOBBIES_1_004": # SCN-02: Stockout
            on_hand = 8
            reserved = 3
            available = 5
            safety_stock = 15
        elif p_id == "FOODS_3_252": # SCN-03: Safety stock breach
            on_hand = int(mean_s * 7) + 5
            reserved = 2
            available = on_hand - reserved
            safety_stock = 45
        elif p_id == "HOUSEHOLD_2_041": # SCN-07: Stale snapshot
            inv_updated_at = "2016-04-18 10:00:00"
            
        inv_records.append({
            "product_id": p_id,
            "product_name": p_name,
            "store_id": store,
            "on_hand_stock": on_hand,
            "reserved_stock": reserved,
            "available_stock": available,
            "safety_stock": safety_stock,
            "inventory_updated_at": inv_updated_at
        })
        
    df_inv = pd.DataFrame(inv_records)
    inv_file = os.path.join(out_dir, "inventory_snapshots.csv")
    df_inv.to_csv(inv_file, index=False)
    print(f"Saved {len(df_inv)} inventory snapshots to {inv_file}")

    # -------------------------------------------------------------
    # 2. SUPPLIER & REPLENISHMENT (500 rows)
    # -------------------------------------------------------------
    print("Generating 500 Supplier & Replenishment records with product_name...")
    cat_supplier_map = {
        "FOODS": ("SUPP_FRESH_01", 2, 50, 400),
        "HOBBIES": ("SUPP_HOBBY_EAST", 4, 20, 200),
        "HOUSEHOLD": ("SUPP_HOME_LOGISTICS", 3, 30, 250)
    }
    
    supp_records = []
    for idx, row in bench_500.iterrows():
        p_id = row["product_id"]
        p_name = row["product_name"]
        cat = row["cat_id"]
        supp_id, lead_time, moq, cap = cat_supplier_map[cat]
        replen_date = "2016-04-26"
        status = "active"
        
        if p_id == "FOODS_2_197": # SCN-05: Late replenishment
            replen_date = "2016-05-06"
            lead_time = 12
        elif p_id == "HOBBIES_1_214": # SCN-06: Suspended supplier
            status = "suspended"
            lead_time = -1
            
        supp_records.append({
            "supplier_id": supp_id,
            "product_id": p_id,
            "product_name": p_name,
            "lead_time_days": lead_time,
            "minimum_order_quantity": moq,
            "replenishment_capacity": cap,
            "expected_replenishment_date": replen_date,
            "supplier_status": status
        })
        
    df_supp = pd.DataFrame(supp_records)
    supp_file = os.path.join(out_dir, "supplier_replenishment.csv")
    df_supp.to_csv(supp_file, index=False)
    print(f"Saved {len(df_supp)} supplier records to {supp_file}")

    # -------------------------------------------------------------
    # 3. CAMPAIGN CATALOGUE (50 rows: 1 segment/row, <= 2 products)
    # -------------------------------------------------------------
    print("Generating exactly 50 campaigns...")
    
    segments_pool = [
        "loyal_members", "budget_conscious", "bulk_buyers", "suburban_families",
        "craft_enthusiasts", "bargain_hunters", "health_conscious", "weekend_shoppers",
        "premium_buyers", "digital_first"
    ]
    campaign_types = [
        "flash_sale", "weekly_special", "clearance", "category_discount", 
        "exclusive_members", "bundle_promotion", "weekend_doorbuster", "seasonal_push"
    ]

    campaigns = []
    cost_records = []
    proposal_records = []
    
    # 10 Benchmark scenario anchors
    anchor_scenarios = [
        {
            "cid": "CAMP-001",
            "name": "Spring Hobbies Creative Flash Sale",
            "ctype": "flash_sale",
            "p_ids": ["HOBBIES_1_001", "HOBBIES_1_002"],
            "segment": "craft_enthusiasts",
            "budget": 5000.0,
            "discount": 0.15,
            "uplift": 0.20,
            "scenario": "SCN-01: Fully Feasible Campaign",
            "fixed_cost": 800.0,
            "cost_contact": 0.08,
            "disc_cost": "retailer_absorbed",
            "logistics": 1.20,
            "acct": "activity_based_costing",
            "expected_b_status": "passed",
            "expected_i_status": "passed",
            "expected_approval": "approved"
        },
        {
            "cid": "CAMP-002",
            "name": "Family Pantry Weekly Saver",
            "ctype": "weekly_special",
            "p_ids": ["FOODS_3_586", "FOODS_3_090"],
            "segment": "bulk_buyers",
            "budget": 8500.0,
            "discount": 0.10,
            "uplift": 0.25,
            "scenario": "SCN-01: Fully Feasible Grocery Campaign",
            "fixed_cost": 1200.0,
            "cost_contact": 0.05,
            "disc_cost": "retailer_absorbed",
            "logistics": 0.85,
            "acct": "activity_based_costing",
            "expected_b_status": "passed",
            "expected_i_status": "passed",
            "expected_approval": "pending_review"
        },
        {
            "cid": "CAMP-003",
            "name": "Hobbies Clearance Blowout",
            "ctype": "clearance",
            "p_ids": ["HOBBIES_1_004"],
            "segment": "bargain_hunters",
            "budget": 3000.0,
            "discount": 0.30,
            "uplift": 0.50,
            "scenario": "SCN-02: Infeasible due to Stockout",
            "fixed_cost": 600.0,
            "cost_contact": 0.12,
            "disc_cost": "clearance_markdown",
            "logistics": 1.50,
            "acct": "direct_costing",
            "expected_b_status": "passed",
            "expected_i_status": "failed_insufficient_stock",
            "expected_approval": "rejected"
        },
        {
            "cid": "CAMP-004",
            "name": "Pantry Essentials Deep Discount",
            "ctype": "category_discount",
            "p_ids": ["FOODS_3_252"],
            "segment": "budget_conscious",
            "budget": 6000.0,
            "discount": 0.25,
            "uplift": 0.35,
            "scenario": "SCN-03: Infeasible due to Safety Stock Breach",
            "fixed_cost": 950.0,
            "cost_contact": 0.06,
            "disc_cost": "retailer_absorbed",
            "logistics": 0.90,
            "acct": "activity_based_costing",
            "expected_b_status": "passed",
            "expected_i_status": "failed_insufficient_stock",
            "expected_approval": "rejected"
        },
        {
            "cid": "CAMP-005",
            "name": "Premium Home Luxury Living Blitz",
            "ctype": "seasonal_push",
            "p_ids": ["HOUSEHOLD_1_032", "HOUSEHOLD_1_118"],
            "segment": "premium_buyers",
            "budget": 750.0, # Budget far below fixed costs
            "discount": 0.20,
            "uplift": 0.30,
            "scenario": "SCN-04: Infeasible due to Budget Limit Violation",
            "fixed_cost": 2000.0,
            "cost_contact": 0.25,
            "disc_cost": "retailer_absorbed",
            "logistics": 3.50,
            "acct": "absorption_costing",
            "expected_b_status": "failed_budget_exceeded",
            "expected_i_status": "passed",
            "expected_approval": "rejected"
        },
        {
            "cid": "CAMP-006",
            "name": "Specialty Fresh Gourmet Showcase",
            "ctype": "weekly_special",
            "p_ids": ["FOODS_2_197"],
            "segment": "health_conscious",
            "budget": 4500.0,
            "discount": 0.15,
            "uplift": 0.40,
            "scenario": "SCN-05: Infeasible due to Replenishment Arriving After Campaign",
            "fixed_cost": 750.0,
            "cost_contact": 0.10,
            "disc_cost": "vendor_co_funded",
            "logistics": 2.00,
            "acct": "activity_based_costing",
            "expected_b_status": "passed",
            "expected_i_status": "failed_replenishment_timing",
            "expected_approval": "rejected"
        },
        {
            "cid": "CAMP-007",
            "name": "Kitchen Renovation & Home Special",
            "ctype": "seasonal_push",
            "p_ids": ["HOUSEHOLD_2_041"],
            "segment": "suburban_families",
            "budget": 5500.0,
            "discount": 0.12,
            "uplift": 0.15,
            "scenario": "SCN-07: Infeasible/Warning due to Stale Inventory Snapshot",
            "fixed_cost": 1100.0,
            "cost_contact": 0.07,
            "disc_cost": "retailer_absorbed",
            "logistics": 1.80,
            "acct": "activity_based_costing",
            "expected_b_status": "passed",
            "expected_i_status": "warning_stale_inventory",
            "expected_approval": "pending_review"
        },
        {
            "cid": "CAMP-008",
            "name": "VIP Club Member Pantry Exclusive",
            "ctype": "exclusive_members",
            "p_ids": ["FOODS_3_090"],
            "segment": "loyal_members",
            "budget": 4000.0,
            "discount": 0.15,
            "uplift": 0.25,
            "scenario": "SCN-08: Competing Campaign A for Shared Inventory",
            "fixed_cost": 850.0,
            "cost_contact": 0.15,
            "disc_cost": "loyalty_reinvestment",
            "logistics": 1.00,
            "acct": "activity_based_costing",
            "expected_b_status": "passed",
            "expected_i_status": "passed",
            "expected_approval": "approved"
        },
        {
            "cid": "CAMP-009",
            "name": "Public Weekend Pantry Bonanza",
            "ctype": "weekend_doorbuster",
            "p_ids": ["FOODS_3_090"],
            "segment": "weekend_shoppers",
            "budget": 4200.0,
            "discount": 0.12,
            "uplift": 0.30,
            "scenario": "SCN-08: Competing Campaign B for Shared Inventory",
            "fixed_cost": 700.0,
            "cost_contact": 0.04,
            "disc_cost": "retailer_absorbed",
            "logistics": 1.00,
            "acct": "activity_based_costing",
            "expected_b_status": "passed",
            "expected_i_status": "passed",
            "expected_approval": "pending_review"
        },
        {
            "cid": "CAMP-010",
            "name": "Collector Series Crafts Launch",
            "ctype": "flash_sale",
            "p_ids": ["HOBBIES_1_214"],
            "segment": "craft_enthusiasts",
            "budget": 3500.0,
            "discount": 0.10,
            "uplift": 0.15,
            "scenario": "SCN-06: Infeasible due to Suspended Supplier",
            "fixed_cost": 500.0,
            "cost_contact": 0.09,
            "disc_cost": "retailer_absorbed",
            "logistics": 1.30,
            "acct": "activity_based_costing",
            "expected_b_status": "passed",
            "expected_i_status": "failed_supplier_unavailable",
            "expected_approval": "rejected"
        }
    ]

    managers_pool = ["MGR-MKT-01", "MGR-MKT-02", "MGR-MKT-03", "MGR-MKT-04", "MGR-MKT-05"]
    approvers_pool = ["APPROVER-SR-01", "APPROVER-SR-02", "APPROVER-EXEC-01"]
    
    # Process anchor scenarios
    for i, s in enumerate(anchor_scenarios):
        cid = s["cid"]
        submitter = managers_pool[i % len(managers_pool)]
        p_ids = s["p_ids"][:2]
        p_names = [product_map.get(pid, build_product_name(pid, pid.split("_")[0], pid.rsplit("_", 1)[0])) for pid in p_ids]
        
        campaigns.append({
            "campaign_id": cid,
            "campaign_name": s["name"],
            "campaign_type": s["ctype"],
            "start_date": campaign_start,
            "end_date": campaign_end,
            "target_product_ids": ";".join(p_ids),
            "target_product_names": "; ".join(p_names),
            "target_segments": s["segment"],
            "campaign_budget": s["budget"],
            "discount_rate": s["discount"],
            "status": "candidate",
            "scenario_label": s["scenario"]
        })
        
        cost_records.append({
            "campaign_id": cid,
            "fixed_campaign_cost": s["fixed_cost"],
            "cost_per_contact": s["cost_contact"],
            "discount_cost_assumption": s["disc_cost"],
            "logistics_cost_assumption": s["logistics"],
            "cost_accounting_method": s["acct"]
        })
        
        proposal_records.append({
            "proposal_id": f"PROP-2016-{i+1:03d}",
            "campaign_id": cid,
            "forecast_version": "m5-dynamic-linear-v2",
            "decision_status": "ranked_feasible" if s["expected_approval"] != "rejected" else "rejected_by_policy",
            "selected_option_id": "OPT-1-STANDARD" if s["expected_approval"] != "rejected" else "NONE",
            "budget_validation_status": s["expected_b_status"],
            "inventory_validation_status": s["expected_i_status"],
            "approval_status": s["expected_approval"],
            "approver_id": approvers_pool[i % len(approvers_pool)] if s["expected_approval"] != "rejected" else "SYSTEM_POLICY_ENGINE",
            "created_at": "2016-04-24 14:00:00",
            "approved_at": "2016-04-24 16:30:00" if s["expected_approval"] == "approved" else ("2016-04-24 14:05:00" if s["expected_approval"] == "rejected" else "")
        })

    # Generate remaining 40 campaigns
    avail_p_ids = bench_500["product_id"].tolist()
    for c_num in range(11, 51):
        cid = f"CAMP-{c_num:03d}"
        n_prods = np.random.choice([1, 2], p=[0.4, 0.6])
        sampled_pids = list(np.random.choice(avail_p_ids, size=n_prods, replace=False))
        sampled_pnames = [product_map[pid] for pid in sampled_pids]
        
        single_segment = np.random.choice(segments_pool)
        ctype = np.random.choice(campaign_types)
        budget = float(np.random.randint(30, 95) * 100)
        discount = round(float(np.random.uniform(0.10, 0.25)), 2)
        status_choice = np.random.choice(["approved", "pending_review", "rejected"], p=[0.60, 0.25, 0.15])
        
        campaigns.append({
            "campaign_id": cid,
            "campaign_name": f"{single_segment.replace('_', ' ').title()} {ctype.replace('_', ' ').title()} #{c_num}",
            "campaign_type": ctype,
            "start_date": campaign_start,
            "end_date": campaign_end,
            "target_product_ids": ";".join(sampled_pids),
            "target_product_names": "; ".join(sampled_pnames),
            "target_segments": single_segment,
            "campaign_budget": budget,
            "discount_rate": discount,
            "status": "candidate",
            "scenario_label": f"SCN-PROD: Standard {ctype.title()} Campaign"
        })
        
        cost_records.append({
            "campaign_id": cid,
            "fixed_campaign_cost": float(np.random.randint(5, 15) * 100),
            "cost_per_contact": round(float(np.random.uniform(0.04, 0.15)), 2),
            "discount_cost_assumption": np.random.choice(["retailer_absorbed", "vendor_co_funded"]),
            "logistics_cost_assumption": round(float(np.random.uniform(0.80, 2.50)), 2),
            "cost_accounting_method": "activity_based_costing"
        })
        
        b_val = "passed" if status_choice != "rejected" else "failed_budget_exceeded"
        i_val = "passed" if status_choice != "rejected" else "failed_insufficient_stock"
        created_time = datetime(2016, 4, 20) + timedelta(hours=int(c_num * 2))
        approved_time = (created_time + timedelta(hours=np.random.randint(1, 10))).strftime("%Y-%m-%d %H:%M:%S") if status_choice != "pending_review" else ""
        
        proposal_records.append({
            "proposal_id": f"PROP-2016-{c_num:03d}",
            "campaign_id": cid,
            "forecast_version": "m5-dynamic-linear-v2",
            "decision_status": "ranked_feasible" if status_choice != "rejected" else "rejected_by_policy",
            "selected_option_id": f"OPT-{np.random.choice(['1-STANDARD', '2-EXPANDED', '3-CONSERVATIVE'])}" if status_choice != "rejected" else "NONE",
            "budget_validation_status": b_val,
            "inventory_validation_status": i_val,
            "approval_status": status_choice,
            "approver_id": np.random.choice(approvers_pool) if status_choice != "rejected" else "SYSTEM_POLICY_ENGINE",
            "created_at": created_time.strftime("%Y-%m-%d %H:%M:%S"),
            "approved_at": approved_time
        })

    # Save campaigns.csv (50 rows)
    df_camp = pd.DataFrame(campaigns)
    camp_file = os.path.join(out_dir, "campaigns.csv")
    df_camp.to_csv(camp_file, index=False)
    print(f"Saved {len(df_camp)} campaigns to {camp_file}")

    # Save campaign_cost_assumptions.csv (50 rows)
    df_costs = pd.DataFrame(cost_records)
    cost_file = os.path.join(out_dir, "campaign_cost_assumptions.csv")
    df_costs.to_csv(cost_file, index=False)
    print(f"Saved {len(df_costs)} cost assumption records to {cost_file}")

    # Save campaign_proposals.csv (50 rows)
    df_props = pd.DataFrame(proposal_records)
    prop_file = os.path.join(out_dir, "campaign_proposals.csv")
    df_props.to_csv(prop_file, index=False)
    print(f"Saved {len(df_props)} proposal records to {prop_file}")

    print("\nCompleted generation of the 5 core synthetic tables.")

if __name__ == "__main__":
    main()
