# Supplier Replenishment, Lead Times & Procurement Protocols

## 1. Overview
This protocol defines procurement constraints, vendor reliability requirements, and replenishment schedule validation for marketing promotions.

## 2. Inbound Replenishment Timing Rule
1. **Dock-to-Stock Requirement**: For a scheduled replenishment order to count towards campaign supply feasibility, its `expected_replenishment_date` must arrive **on or before the campaign start date** (`2016-04-25`).
2. **Late Replenishment Violation**:
   - If an inbound shipment arrives *after* the campaign start date (or after campaign end date `2016-05-01`), it cannot fulfill promotional demand.
   - Any campaign proposal that relies on replenishment arriving after the promotional window must be rejected immediately (`failed_replenishment_timing`).

## 3. Supplier Status & Lead Time Validation
1. **Active Vendor Status**:
   - The supplier associated with a targeted item must have `supplier_status = 'active'`.
   - If `supplier_status = 'suspended'` or `'inactive'`, the proposal must be rejected (`failed_supplier_unavailable`).
2. **Missing Lead Time Data**:
   - Lead time must be a positive integer ($\ge 1$).
   - If `lead_time_days` is null, unknown, or recorded as `-1`, the system cannot calculate dynamic safety stock. The proposal must be flagged with `rejected_missing_supplier_lead_time`.

## 4. Minimum Order Quantity (MOQ) and Supplier Capacity
1. **MOQ Enforcement**: Purchase orders triggered for campaign restock cannot be smaller than the vendor's agreed `minimum_order_quantity` (typically 20–50 units).
2. **Batch Capacity**: The total inbound quantity cannot exceed the vendor's maximum batch fulfillment `replenishment_capacity` (typically 200–400 units).

