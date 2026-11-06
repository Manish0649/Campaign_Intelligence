# Campaign Playbooks & Benchmark Scenario Guidelines

## 1. Promotional Playbooks by Campaign Type
1. **Flash Sale (`flash_sale`)**:
   - **Characteristics**: Short duration, steep discounts (15%–25%), high demand velocity.
   - **Supply Buffer**: Requires safety stock coverage of at least 1.8x standard volatility.
   - **Target Segments**: `craft_enthusiasts`, `bargain_hunters`, `deal_seekers`.
   - **Recommended Uplift Scenario**: +20% to +35%.
2. **Weekly Special (`weekly_special`)**:
   - **Characteristics**: Regular scheduled grocery promotions, moderate discount (10%–15%).
   - **Supply Buffer**: High stock turnover; heavily relies on recurring 2-day supplier delivery schedules.
   - **Target Segments**: `bulk_buyers`, `suburban_families`.
   - **Recommended Uplift Scenario**: +15% to +25%.
3. **Clearance Markdown (`clearance`)**:
   - **Characteristics**: Liquidation of end-of-life or overstocked merchandise (25%–35% discount).
   - **Supply Buffer**: No supplier replenishment; sales must strictly consume available on-hand stock without safety stock constraints.
   - **Target Segments**: `bargain_hunters`.
4. **Member Exclusive (`exclusive_members`)**:
   - **Characteristics**: Targeted promotions for high-tier loyalty members (12%–18% discount).
   - **Supply Buffer**: Modest total demand volume with high conversion rates; low stockout risk.
   - **Target Segments**: `loyal_members`, `premium_buyers`.

## 2. Benchmark Scenario Root-Cause Analysis Matrix
When reviewing feasibility engine decisions, proposals will map to one of the following root causes:

| Scenario Code | Scenario Type | Policy Evaluation | Corrective Operational Action |
| :--- | :--- | :--- | :--- |
| **SCN-01** | Fully Feasible | `feasible_for_review` | Route to human approver for sign-off. |
| **SCN-02** | Stockout Violation | `failed_insufficient_stock` | Increase inventory allocation or lower campaign uplift. |
| **SCN-03** | Safety Stock Breach | `failed_safety_stock_breach` | Reduce discount rate or trigger emergency vendor restock. |
| **SCN-04** | Budget Violation | `failed_budget_exceeded` | Downscale audience reach or negotiate vendor co-funding. |
| **SCN-05** | Late Replenishment | `failed_replenishment_timing` | Delay campaign start date to match supplier dock date. |
| **SCN-06** | Supplier Inactive | `failed_supplier_unavailable` | Switch to alternate qualified vendor before drafting proposal. |
| **SCN-07** | Stale Inventory | `warning_stale_inventory` | Conduct warehouse cycle count and update snapshot timestamp. |
| **SCN-08** | Competing Campaigns | `competing_demand_conflict` | Prioritize by expected gross margin contribution or separate run dates. |

