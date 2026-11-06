# Inventory Feasibility, Safety Stock & Data Freshness Policy

## 1. Overview
Promotional campaigns that generate demand exceeding available stock result in backorders, lost margin, customer dissatisfaction, and fulfillment penalties. This policy governs how warehouse and store inventory availability must be evaluated.

## 2. Inventory Availability Equations
1. **Physical On-Hand Stock**:
   Physical count of inventory located in the designated distribution center or store (`CA_1`).
2. **Reserved Stock**:
   Stock committed to existing customer orders, wholesale allocations, or in-transit store transfers (standardized at 15% of on-hand stock).
3. **Safety Stock Formula**:
   Mandatory protective buffer to absorb forecast uncertainty and supplier lead time variability:
   $$\text{Safety Stock} = \lceil Z \times \sqrt{L} \times \sigma_{\text{daily}} \rceil$$
   - $Z = 1.65$ (standard normal quantile corresponding to a 95% service level).
   - $L = \text{Supplier Lead Time in Days}$ (default 3 days).
   - $\sigma_{\text{daily}} = \text{Standard deviation of daily sales over the trailing 30 days}$.
4. **Net Usable Stock for Campaign Demand**:
   $$\text{Net Usable Stock} = \text{On-Hand Stock} - \text{Reserved Stock} - \text{Safety Stock}$$
   If safety stock is breached, the proposal triggers a `rejected_safety_stock_violation`.

## 3. Supply-Demand Balance Feasibility Check
A campaign proposal is deemed supply-feasible if and only if:
$$\text{Projected Supply} \ge \text{Baseline Demand Forecast} \times (1 + \text{assumed\_uplift\_pct})$$
Where:
$$\text{Projected Supply} = \text{Net Usable Stock} + \sum \text{Confirmed Replenishment Arrival}_{(\text{arrival\_date} \le \text{campaign\_start\_date})}$$

## 4. Operational Data Freshness Rules (Rule 9)
1. **Snapshot Staleness Threshold**: Inventory snapshots must have an `inventory_updated_at` timestamp within **72 hours** of the campaign planning evaluation.
2. **Stale Data Penalty**: Any inventory snapshot older than 72 hours triggers an operational warning (`warning_stale_inventory`) and blocks automatic approval until manual warehouse cycle-count verification.
3. **Missing Data Handling**: If inventory records for a targeted product are missing, the system must never assume zero or infinite stock. It must return `rejected_missing_inventory_evidence`.

