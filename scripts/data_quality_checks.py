"""Run deterministic checks against the project's processed CSV artifacts."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
PROCESSED = BASE_DIR / "data" / "processed" / "clean_db_ready"
REPORT = BASE_DIR / "docs" / "current_data_quality_audit.md"


def _read_csv(name: str, required: set[str]) -> tuple[pd.DataFrame | None, list[str]]:
    path = PROCESSED / name
    if not path.exists():
        return None, [f"Missing required file: {name}"]
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        return None, [f"Could not read {name}: {type(exc).__name__}"]
    missing = sorted(required - set(frame.columns))
    issues = [f"{name} is missing columns: {', '.join(missing)}"] if missing else []
    return frame, issues


def run_checks() -> dict:
    results: dict[str, dict] = {}
    errors: list[str] = []
    warnings: list[str] = []

    products, issues = _read_csv("dim_products.csv", {"product_id", "product_name", "base_price"})
    errors.extend(issues)
    if products is not None:
        prices = pd.to_numeric(products["base_price"], errors="coerce")
        results["products"] = {
            "rows": len(products),
            "duplicate_product_ids": int(products["product_id"].duplicated().sum()),
            "missing_product_ids": int(products["product_id"].isna().sum()),
            "invalid_prices": int((prices.isna() | (prices <= 0)).sum()),
        }
        if results["products"]["duplicate_product_ids"] or results["products"]["missing_product_ids"] or results["products"]["invalid_prices"]:
            errors.append("Product dimension contains duplicate/missing IDs or non-positive prices.")

    campaigns, issues = _read_csv("dim_campaigns.csv", {"campaign_id", "start_date", "end_date", "campaign_budget"})
    errors.extend(issues)
    if campaigns is not None:
        starts = pd.to_datetime(campaigns["start_date"], errors="coerce")
        ends = pd.to_datetime(campaigns["end_date"], errors="coerce")
        budgets = pd.to_numeric(campaigns["campaign_budget"], errors="coerce")
        results["campaigns"] = {
            "rows": len(campaigns),
            "duplicate_campaign_ids": int(campaigns["campaign_id"].duplicated().sum()),
            "invalid_dates": int((starts.isna() | ends.isna() | (ends < starts)).sum()),
            "invalid_budgets": int((budgets.isna() | (budgets <= 0)).sum()),
        }
        if any(results["campaigns"][key] for key in ("duplicate_campaign_ids", "invalid_dates", "invalid_budgets")):
            errors.append("Campaign dimension contains duplicate IDs, invalid date windows or invalid budgets.")

    inventory, issues = _read_csv("fct_inventory_snapshots.csv", {"product_id", "store_id", "on_hand_stock", "reserved_stock", "available_stock", "safety_stock"})
    errors.extend(issues)
    if inventory is not None:
        numeric = inventory[["on_hand_stock", "reserved_stock", "available_stock", "safety_stock"]].apply(pd.to_numeric, errors="coerce")
        results["inventory"] = {
            "rows": len(inventory),
            "duplicate_product_store_keys": int(inventory.duplicated(["product_id", "store_id"]).sum()),
            "invalid_numeric_rows": int(numeric.isna().any(axis=1).sum()),
            "negative_stock_rows": int((numeric < 0).any(axis=1).sum()),
            "available_stock_mismatch_rows": int((numeric["available_stock"] != numeric["on_hand_stock"] - numeric["reserved_stock"]).sum()),
        }
        if any(results["inventory"][key] for key in ("duplicate_product_store_keys", "invalid_numeric_rows", "negative_stock_rows", "available_stock_mismatch_rows")):
            errors.append("Inventory snapshots contain key, numeric, negative-stock or availability-balance violations.")

    daily_sales, issues = _read_csv("fct_daily_sales.csv", {"product_id", "store_id", "date", "sales_units", "sell_price"})
    errors.extend(issues)
    if daily_sales is not None:
        sales_units = pd.to_numeric(daily_sales["sales_units"], errors="coerce")
        sell_prices = pd.to_numeric(daily_sales["sell_price"], errors="coerce")
        sales_dates = pd.to_datetime(daily_sales["date"], errors="coerce")
        results["daily_sales"] = {
            "rows": len(daily_sales),
            "duplicate_product_store_date_keys": int(daily_sales.duplicated(["product_id", "store_id", "date"]).sum()),
            "invalid_dates": int(sales_dates.isna().sum()),
            "invalid_sales_units": int((sales_units.isna() | (sales_units < 0)).sum()),
            "invalid_sell_prices": int((sell_prices.isna() | (sell_prices <= 0)).sum()),
        }
        if any(results["daily_sales"][key] for key in ("duplicate_product_store_date_keys", "invalid_dates", "invalid_sales_units", "invalid_sell_prices")):
            errors.append("Daily sales contain duplicate keys or invalid dates, units or prices.")

    cost_assumptions, issues = _read_csv(
        "fct_campaign_cost_assumptions.csv",
        {"campaign_id", "fixed_campaign_cost", "cost_per_contact", "logistics_cost_assumption"},
    )
    errors.extend(issues)
    if cost_assumptions is not None:
        cost_cols = ["fixed_campaign_cost", "cost_per_contact", "logistics_cost_assumption"]
        numeric_costs = cost_assumptions[cost_cols].apply(pd.to_numeric, errors="coerce")
        results["campaign_cost_assumptions"] = {
            "rows": len(cost_assumptions),
            "duplicate_campaign_ids": int(cost_assumptions["campaign_id"].duplicated().sum()),
            "invalid_cost_rows": int((numeric_costs.isna() | (numeric_costs < 0)).any(axis=1).sum()),
        }
        if results["campaign_cost_assumptions"]["duplicate_campaign_ids"] or results["campaign_cost_assumptions"]["invalid_cost_rows"]:
            errors.append("Campaign cost assumptions contain duplicate campaign IDs or invalid negative/missing costs.")

    suppliers, issues = _read_csv("fct_supplier_replenishment.csv", {"supplier_id", "product_id", "lead_time_days", "minimum_order_quantity", "replenishment_capacity", "expected_replenishment_date", "supplier_status"})
    errors.extend(issues)
    if suppliers is not None:
        lead = pd.to_numeric(suppliers["lead_time_days"], errors="coerce")
        moq = pd.to_numeric(suppliers["minimum_order_quantity"], errors="coerce")
        capacity = pd.to_numeric(suppliers["replenishment_capacity"], errors="coerce")
        results["suppliers"] = {
            "rows": len(suppliers),
            "duplicate_supplier_product_keys": int(suppliers.duplicated(["supplier_id", "product_id"]).sum()),
            "missing_lead_time_rows": int(lead.isna().sum()),
            "non_positive_lead_time_rows": int((lead.notna() & (lead <= 0)).sum()),
            "invalid_moq_rows": int((moq.isna() | (moq <= 0)).sum()),
            "capacity_below_moq_rows": int((capacity.isna() | (capacity < moq)).sum()),
            "non_active_supplier_rows": int((suppliers["supplier_status"].astype(str).str.lower() != "active").sum()),
        }
        if any(results["suppliers"][key] for key in ("duplicate_supplier_product_keys", "non_positive_lead_time_rows", "invalid_moq_rows", "capacity_below_moq_rows")):
            errors.append("Supplier replenishment records contain invalid keys or operational constraints.")
        if results["suppliers"]["missing_lead_time_rows"] or results["suppliers"]["non_active_supplier_rows"]:
            warnings.append(
                "Some supplier records are intentionally unavailable (missing lead time or suspended status); "
                "the feasibility engine must reject campaigns relying on those records."
            )

    # Cross-table product references are checked when the dimension is available.
    if products is not None:
        product_ids = set(products["product_id"].dropna().astype(str))
        for table_name, frame in (("inventory", inventory), ("suppliers", suppliers), ("daily_sales", daily_sales)):
            if frame is not None:
                orphan_count = int((~frame["product_id"].astype(str).isin(product_ids)).sum())
                results[table_name]["orphan_product_references"] = orphan_count
                if orphan_count:
                    errors.append(f"{table_name} contains {orphan_count} product references absent from dim_products.")
        if campaigns is not None:
            referenced = set()
            for raw_ids in campaigns.get("target_product_ids", pd.Series(dtype=str)).fillna("").astype(str):
                referenced.update(item.strip() for item in raw_ids.split(";") if item.strip())
            missing_campaign_products = sorted(referenced - product_ids)
            results["campaigns"]["unknown_target_product_ids"] = len(missing_campaign_products)
            if missing_campaign_products:
                errors.append("Campaigns reference product IDs absent from dim_products: " + ", ".join(missing_campaign_products[:10]))
        if cost_assumptions is not None and campaigns is not None:
            campaign_ids = set(campaigns["campaign_id"].dropna().astype(str))
            orphan_costs = int((~cost_assumptions["campaign_id"].astype(str).isin(campaign_ids)).sum())
            results["campaign_cost_assumptions"]["orphan_campaign_references"] = orphan_costs
            if orphan_costs:
                errors.append(f"Campaign cost assumptions contain {orphan_costs} campaign references absent from dim_campaigns.")

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "failed" if errors else ("passed_with_warnings" if warnings else "passed"),
        "errors": errors,
        "warnings": warnings,
        "results": results,
    }


def main() -> None:
    report = run_checks()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Current Data Quality Audit",
        "",
        f"- Generated: `{report['generated_at_utc']}`",
        f"- Status: **{report['status'].upper()}**",
        "",
        "## Table checks",
        "",
    ]
    for table, metrics in report["results"].items():
        lines.extend([f"### {table}", "", "| Check | Result |", "|---|---:|"])
        lines.extend([f"| {key} | {value} |" for key, value in metrics.items()])
        lines.append("")
    lines.extend(["## Errors", ""])
    lines.extend([f"- {error}" for error in report["errors"]] or ["- No structural data quality errors detected."])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {warning}" for warning in report["warnings"]] or ["- No warnings."])
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Report written to: {REPORT}")
    if report["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
