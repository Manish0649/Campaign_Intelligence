# Current Data Quality Audit

- Generated: `2026-11-05T17:31:49.374620+00:00`
- Status: **PASSED_WITH_WARNINGS**

## Table checks

### products

| Check | Result |
|---|---:|
| rows | 500 |
| duplicate_product_ids | 0 |
| missing_product_ids | 0 |
| invalid_prices | 0 |

### campaigns

| Check | Result |
|---|---:|
| rows | 50 |
| duplicate_campaign_ids | 0 |
| invalid_dates | 0 |
| invalid_budgets | 0 |
| unknown_target_product_ids | 0 |

### inventory

| Check | Result |
|---|---:|
| rows | 500 |
| duplicate_product_store_keys | 0 |
| invalid_numeric_rows | 0 |
| negative_stock_rows | 0 |
| available_stock_mismatch_rows | 0 |
| orphan_product_references | 0 |

### daily_sales

| Check | Result |
|---|---:|
| rows | 182500 |
| duplicate_product_store_date_keys | 0 |
| invalid_dates | 0 |
| invalid_sales_units | 0 |
| invalid_sell_prices | 0 |
| orphan_product_references | 0 |

### campaign_cost_assumptions

| Check | Result |
|---|---:|
| rows | 50 |
| duplicate_campaign_ids | 0 |
| invalid_cost_rows | 0 |
| orphan_campaign_references | 0 |

### suppliers

| Check | Result |
|---|---:|
| rows | 500 |
| duplicate_supplier_product_keys | 0 |
| missing_lead_time_rows | 1 |
| non_positive_lead_time_rows | 0 |
| invalid_moq_rows | 0 |
| capacity_below_moq_rows | 0 |
| non_active_supplier_rows | 1 |
| orphan_product_references | 0 |

## Errors

- No structural data quality errors detected.

## Warnings

- Some supplier records are intentionally unavailable (missing lead time or suspended status); the feasibility engine must reject campaigns relying on those records.
