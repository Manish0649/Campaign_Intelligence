# Campaign Planning & Budget Governance Policy

## 1. Overview & Objective
This policy defines mandatory financial, operational, and structural rules for drafting, evaluating, and launching retail promotional campaigns within the Campaign Intelligence system.

## 2. Hard Budget Constraint (Rule 2)
1. **Budget Ceiling**: Every candidate campaign must have an explicit `campaign_budget`. Under no circumstances can a campaign be approved if its total projected cost exceeds the configured budget limit.
2. **Cost Calculation Formula**:
   $$\text{Total Projected Cost} = \text{Fixed Setup Cost} + (\text{Target Audience Size} \times \text{Cost per Contact}) + (\text{Projected Campaign Units} \times \text{Sell Price} \times \text{Discount Rate}) + (\text{Projected Campaign Units} \times \text{Logistics Surcharge})$$
3. **Cost Components**:
   - **Fixed Setup Cost**: Base creative, platform, and channel configuration fee ($500 – $2,000).
   - **Variable Contact Cost**: Direct outreach messaging expense (SMS, push, targeted email: $0.04 – $0.15 per contact).
   - **Discount Cost**: Cost of markdowns. Unless explicitly designated as `vendor_co_funded`, markdown expenses are absorbed 100% by the retailer.
   - **Logistics Surcharge**: Incremental warehouse pick, pack, and transport handling surcharge ($0.80 – $3.50 per unit).

## 3. Campaign Structure & Scoping Rules
1. **Duration Window**: Standard campaigns run for a 7-day promotional horizon (Monday through Sunday).
2. **Audience Segmentation**: Each campaign must target strictly **one** primary customer segment (e.g., `craft_enthusiasts`, `bulk_buyers`, `budget_conscious`, `loyal_members`, `suburban_families`). Multi-segment broadcasting is prohibited to maintain clean response attribution.
3. **Product Scope**: A campaign may target at most **2 product IDs** simultaneously. This ensures focused inventory commitment and avoids cross-category cannibalization.
4. **Assumed Uplift Transparency (Rule 6)**: Baseline demand forecasts represent expected sales under business-as-usual conditions. Any promotional demand increment must be explicitly documented as an `assumed_uplift_pct` (e.g., 0.20 for +20% demand) and must not be presented as a causal certainty.

