# Dataset Documentation & Synthetic Data Architecture

## 1. Project Overview & Scope
- **Project**: Campaign Intelligence with Demand and Supply Planning
- **Primary Objective**: Forecast retail demand, validate promotional campaigns against deterministic supply, safety stock, and budget constraints, and provide an auditable approval workflow before activation.
- **Primary Historical Source**: M5 Forecasting (Walmart retail daily sales from 2011 to 2016).
- **Secondary / Exploratory Sources**: DataCo Smart Supply Chain, UCI Online Retail II, UCI Bank Marketing.
- **Operational Data**: Exactly **5 core synthetic tables** generated per **Section 3.5** of the project specification.

---

## 2. Directory Layout

```
data/
├── raw/
│   ├── m5/
│   │   ├── calendar.csv                  # 1,969 days (2011-01-29 to 2016-06-19)
│   │   ├── sales_train_validation.csv    # 30,490 series, daily unit sales d_1 to d_1913
│   │   ├── sales_train_evaluation.csv    # 30,490 series, daily unit sales d_1 to d_1941
│   │   ├── sell_prices.csv               # Weekly sell prices by store_id and item_id
│   │   └── sample_submission.csv
│   ├── dataco/                           # Supply chain logistics & risk data (exploratory)
│   ├── online_retail_II/                 # Customer purchasing patterns (exploratory)
│   └── bank_marketing/                   # Direct contact marketing dataset (exploratory)
└── processed/
    └── synthetic/                        # The 5 Core Operational Datasets
        ├── campaigns.csv                 # 50 promotional campaign records
        ├── campaign_cost_assumptions.csv # 50 cost accounting records matched to campaigns
        ├── campaign_proposals.csv        # 50 auditable proposal decisions linking rules & outcomes
        ├── inventory_snapshots.csv       # 500 stock position records with product_name
        └── supplier_replenishment.csv    # 500 procurement records with product_name
```

---

## 3. Dataset Schemas (Section 3.5 Compliance)

### 3.1 `campaigns.csv` (50 Rows)
- `target_segments`: Exactly **1 target segment** per row.
- `target_product_ids`: **At most 2 product IDs** per row (separated by `;`).
- `target_product_names`: Real retail product names for each product ID.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `campaign_id` | String | `CAMP-001` through `CAMP-050` |
| `campaign_name` | String | Descriptive title |
| `campaign_type` | String | `flash_sale`, `weekly_special`, `clearance`, `category_discount`, etc. |
| `start_date` | Date | `2016-04-25` (7-day promotional window start) |
| `end_date` | Date | `2016-05-01` (7-day promotional window end) |
| `target_product_ids` | String | 1 or 2 M5 product identifiers |
| `target_product_names`| String | Human-readable names of targeted products |
| `target_segments` | String | **Single** targeted audience segment |
| `campaign_budget` | Float | Maximum allowed campaign budget ($) |
| `discount_rate` | Float | Price markdown percentage (0.10 to 0.30) |
| `status` | String | `candidate` |
| `scenario_label` | String | Scenario description (SCN-01 to SCN-08) |

### 3.2 `campaign_cost_assumptions.csv` (50 Rows)
Matches 1-to-1 with `campaigns.csv`. Contains fixed creative costs, cost-per-contact, discount subsidy policies, and unit logistics surcharges.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `campaign_id` | String | Foreign key to `campaigns.csv` |
| `fixed_campaign_cost` | Float | Base platform & setup cost ($500.00 – $2,000.00) |
| `cost_per_contact` | Float | Variable messaging/SMS/email cost ($0.04 – $0.15) |
| `discount_cost_assumption` | String | `retailer_absorbed`, `vendor_co_funded`, `clearance_markdown` |
| `logistics_cost_assumption` | Float | Surcharge per unit shipped ($0.80 – $3.50) |
| `cost_accounting_method` | String | `activity_based_costing`, `direct_costing`, `absorption_costing` |

### 3.3 `campaign_proposals.csv` (50 Rows)
Matches 1-to-1 with `campaigns.csv`. Stores the state machine lifecycle for each campaign proposal:
- `proposal_id`: `PROP-2016-001` to `PROP-2016-050`
- `campaign_id`: Foreign key to `campaigns.csv`
- `forecast_version`: Forecasting model version (`m5-baseline-v1.0`)
- `decision_status`: `ranked_feasible` or `rejected_by_policy`
- `selected_option_id`: `OPT-1-STANDARD`, `OPT-2-EXPANDED`, `NONE`
- `budget_validation_status`: `passed` or `failed_budget_exceeded`
- `inventory_validation_status`: `passed`, `failed_insufficient_stock`, `failed_replenishment_timing`, etc.
- `approval_status`: `approved`, `pending_review`, or `rejected`
- `approver_id`: Authority user ID or `SYSTEM_POLICY_ENGINE`
- `created_at`, `approved_at`: Audit timestamps

### 3.4 `inventory_snapshots.csv` (500 Rows)
Stock position of 500 M5 benchmark products in store `CA_1`:
- `product_id`: M5 item identifier
- `product_name`: Descriptive product name (e.g. `Deluxe Acrylic Craft Paint Set (#1)`)
- `store_id`: `CA_1`
- `on_hand_stock`: Physical units in warehouse
- `reserved_stock`: Committed units (15%)
- `available_stock`: Net available units (`on_hand - reserved`)
- `safety_stock`: $\lceil 1.65 \times \sqrt{L} \times \sigma_{\text{daily}} \rceil$
- `inventory_updated_at`: Point-in-time timestamp (`2016-04-24 23:59:00`)

### 3.5 `supplier_replenishment.csv` (500 Rows)
Procurement records for the 500 benchmark items:
- `supplier_id`, `product_id`, `product_name`, `lead_time_days`, `minimum_order_quantity`, `replenishment_capacity`, `expected_replenishment_date`, `supplier_status` (`active` / `suspended`).

---

## 4. Benchmark Scenario Test Matrix

| Campaign ID | Scenario Description | Expected Outcome | Constraint / Rule Tested |
| :--- | :--- | :--- | :--- |
| `CAMP-001` | Spring Hobbies Flash Sale | **Feasible for Review** | All constraints pass; stock > baseline + 20% uplift + safety stock. |
| `CAMP-002` | Family Pantry Weekly Saver | **Feasible for Review** | Fast moving grocery items; budget and replenishment confirmed. |
| `CAMP-003` | Hobbies Clearance Blowout | **Rejected** | `failed_insufficient_stock`: Available stock (5) < Demand (50+). |
| `CAMP-004` | Pantry Essentials Deep Discount | **Rejected** | `failed_safety_stock_breach`: Dips into mandatory safety stock (45). |
| `CAMP-005` | Premium Luxury Living Blitz | **Rejected** | `failed_budget_exceeded`: Budget ($750) < Fixed setup cost ($2,000). |
| `CAMP-006` | Specialty Gourmet Showcase | **Rejected** | `failed_replenishment_timing`: Inbound shipment arrives after campaign. |
| `CAMP-007` | Kitchen Renovation Special | **Warning / Infeasible** | `warning_stale_inventory`: Snapshot updated 6 days ago (> 72 hours). |
| `CAMP-008` | VIP Exclusive Pantry | **Feasible Individually** | Competes with `CAMP-009` for `FOODS_3_090` inventory. |
| `CAMP-009` | Public Weekend Pantry | **Feasible Individually** | Competes with `CAMP-008` for `FOODS_3_090` inventory. |
| `CAMP-010` | Collector Crafts Series | **Rejected** | `failed_supplier_unavailable`: Supplier status is `suspended`. |
