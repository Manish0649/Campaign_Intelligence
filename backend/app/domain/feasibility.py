from datetime import date, datetime
from math import isfinite
from typing import List, Dict, Any, Optional

from backend.app.api.schemas.proposal import (
    FeasibilityRequest, FeasibilityResponse, ProductFeasibilityDetail
)
from backend.app.api.schemas.campaign import CampaignCostAssumption
from backend.app.domain.budget import calculate_campaign_cost, validate_campaign_budget
from backend.app.domain.inventory import validate_inventory_availability
from backend.app.domain.replenishment import validate_supplier_and_replenishment

def evaluate_campaign_feasibility(
    request: FeasibilityRequest,
    campaign_budget: float,
    discount_rate: float,
    cost_assumptions: CampaignCostAssumption,
    product_data: Dict[str, Dict[str, Any]],
    evaluation_time: Optional[datetime] = None
) -> FeasibilityResponse:
    """
    Core Deterministic Feasibility Engine (Day 4 Deliverable)
    Evaluates:
      1. Structural constraints (duration <= 7 days, max 2 product IDs)
      2. Baseline & Scenario Forecast Demand Check
      3. Inventory Availability & Safety Stock Checks
      4. Replenishment Arrival & Vendor Reliability
      5. Supply-Demand Balance Feasibility
      6. Hard Budget Ceiling Check
    """
    warnings: List[str] = []
    rejection_reasons: List[str] = []
    
    # 1. Structural Checks
    duration_days = (request.end_date - request.start_date).days + 1
    if duration_days > 7:
        warnings.append(f"warning_non_standard_duration: Campaign duration ({duration_days} days) exceeds standard 7-day window")
    if duration_days <= 0:
        rejection_reasons.append("rejected_invalid_dates: end_date must be on or after start_date")

    if len(request.product_ids) > 2:
        rejection_reasons.append("rejected_product_scope_exceeded: Campaign targets more than 2 products simultaneously")
        
    product_details: List[ProductFeasibilityDetail] = []
    total_projected_units = 0.0
    weighted_sell_price_sum = 0.0
    
    all_forecasts_passed = True
    all_inventory_passed = True
    all_replenishment_passed = True
    
    # Evaluate per product
    for pid in request.product_ids:
        p_info = product_data.get(pid)
        if not p_info:
            rejection_reasons.append(f"rejected_missing_product_evidence: Product '{pid}' not found in catalogue")
            all_forecasts_passed = False
            all_inventory_passed = False
            continue

        # A baseline forecast is mandatory evidence. Never invent a fallback value.
        raw_baseline = p_info.get("baseline_forecast")
        try:
            baseline_units = float(raw_baseline)
        except (TypeError, ValueError):
            baseline_units = float("nan")

        if not isfinite(baseline_units) or baseline_units < 0:
            rejection_reasons.append(
                f"rejected_missing_or_invalid_forecast: No valid baseline forecast for '{pid}'"
            )
            all_forecasts_passed = False
            continue

        inv_snapshot = p_info.get("inventory")
        if not inv_snapshot:
            rejection_reasons.append(f"rejected_missing_inventory_evidence: Missing inventory snapshot for '{pid}'")
            all_inventory_passed = False
            continue

        supp_info = p_info.get("supplier")
        if not supp_info:
            warnings.append(f"warning_missing_supplier: No supplier replenishment record found for '{pid}'")

        promotional_units = baseline_units * (1.0 + float(request.assumed_uplift_pct))
        total_projected_units += promotional_units

        # Registered product price is required financial evidence. Never insert
        # a synthetic default price into campaign cost calculations.
        raw_price = p_info.get("base_price")
        try:
            base_price = float(raw_price)
        except (TypeError, ValueError):
            base_price = float("nan")
        if not isfinite(base_price) or base_price <= 0:
            rejection_reasons.append(
                f"rejected_missing_or_invalid_product_price: No valid registered base price for '{pid}'"
            )
            base_price = 0.0
        weighted_sell_price_sum += base_price * promotional_units
        
        # Inventory Validation
        inv_eval = validate_inventory_availability(
            on_hand_stock=int(inv_snapshot.get("on_hand_stock", 0)),
            reserved_stock=int(inv_snapshot.get("reserved_stock", 0)),
            safety_stock=int(inv_snapshot.get("safety_stock", 0)),
            snapshot_timestamp=inv_snapshot.get("inventory_updated_at"),
            reference_time=evaluation_time
        )
        warnings.extend(inv_eval["warnings"])
        if inv_eval["rejection_reasons"]:
            rejection_reasons.extend(inv_eval["rejection_reasons"])
            all_inventory_passed = False
            
        # Replenishment Validation
        replen_units = 0
        replen_status = "failed"

        replen_warnings = []
        replen_rejection_reasons = []

        if not supp_info:
            all_replenishment_passed = False

            replen_rejection_reasons.append(
                f"rejected_missing_supplier_evidence: "
                f"No supplier replenishment record found for '{pid}'"
            )

        else:
            replen_eval = validate_supplier_and_replenishment(
                supplier_id=supp_info["supplier_id"],
                supplier_status=supp_info["supplier_status"],
                lead_time_days=supp_info["lead_time_days"],
                minimum_order_quantity=supp_info["minimum_order_quantity"],
                replenishment_capacity=supp_info["replenishment_capacity"],
                expected_replenishment_date=supp_info["expected_replenishment_date"],
                campaign_start_date=request.start_date,
                campaign_end_date=request.end_date
            )

            replen_warnings.extend(replen_eval["warnings"])
            replen_rejection_reasons.extend(
                replen_eval["rejection_reasons"]
            )

            if replen_eval["rejection_reasons"]:
                all_replenishment_passed = False
            else:
                replen_status = "passed"

            replen_units = replen_eval["usable_replenishment_units"]

        warnings.extend(replen_warnings)
        rejection_reasons.extend(replen_rejection_reasons)
                    
        # Supply vs Demand check
        net_usable = inv_eval["net_usable_stock"]
        projected_supply = net_usable + replen_units
        projected_surplus = round(projected_supply - promotional_units, 2)
        
        if projected_supply < promotional_units:
            rejection_reasons.append(
                f"failed_insufficient_stock: Product '{pid}' projected supply ({projected_supply}) is less than campaign demand ({promotional_units:.1f})"
            )
            all_inventory_passed = False
            inv_detail_status = "failed_insufficient_stock"
        else:
            inv_detail_status = inv_eval["status"]
            
        product_details.append(
            ProductFeasibilityDetail(
                product_id=pid,
                product_name=p_info.get("product_name", pid),
                baseline_forecast_units=round(baseline_units, 2),
                promotional_demand_units=round(promotional_units, 2),
                on_hand_stock=inv_eval["on_hand_stock"],
                reserved_stock=inv_eval["reserved_stock"],
                safety_stock=inv_eval["safety_stock"],
                net_usable_stock=net_usable,
                confirmed_replenishment_units=replen_units,
                projected_supply=projected_supply,
                projected_surplus=projected_surplus,
                inventory_validation_status=inv_detail_status,
                replenishment_validation_status=replen_status,
                warnings=inv_eval["warnings"] + replen_warnings,
                rejection_reasons=(inv_eval["rejection_reasons"] + replen_rejection_reasons)
            )
        )
        
    # Budget Check
    avg_sell_price = (weighted_sell_price_sum / total_projected_units) if total_projected_units > 0 else 0.0
    effective_budget = campaign_budget
    
    total_cost, cost_breakdown = calculate_campaign_cost(
        fixed_setup_cost=cost_assumptions.fixed_campaign_cost,
        target_audience_size=request.target_audience_size or 5000,
        cost_per_contact=cost_assumptions.cost_per_contact,
        projected_campaign_units=total_projected_units,
        sell_price=avg_sell_price,
        discount_rate=discount_rate,
        logistics_surcharge=cost_assumptions.logistics_cost_assumption,
        discount_cost_assumption=cost_assumptions.discount_cost_assumption
    )
    
    budget_ok, budget_status, budget_remaining = validate_campaign_budget(
        campaign_budget=effective_budget,
        total_projected_cost=total_cost
    )
    if not budget_ok:
        rejection_reasons.append(
            f"failed_budget_exceeded: Total projected cost (${total_cost:,.2f}) exceeds configured budget (${effective_budget:,.2f})"
        )
        
    overall_inventory_status = "passed" if all_inventory_passed else "failed"
    overall_replenishment_status = "passed" if all_replenishment_passed else "failed"
    overall_budget_status = "passed" if budget_ok else "failed"
    
    is_feasible = (
        budget_ok and
        all_forecasts_passed and
        all_inventory_passed and
        all_replenishment_passed and 
        len(rejection_reasons) == 0
    )
    
    return FeasibilityResponse(
        campaign_id=request.campaign_id,
        status="feasible_for_review" if is_feasible else "rejected_by_policy",
        forecast_version="m5-dynamic-linear-v2",
        forecast_validation="passed" if all_forecasts_passed else "failed",
        budget_validation=overall_budget_status,
        inventory_validation=overall_inventory_status,
        replenishment_validation=overall_replenishment_status,
        total_projected_cost=total_cost,
        budget_limit=effective_budget,
        warnings=warnings,
        rejection_reasons=rejection_reasons,
        approval_required=True,
        product_details=product_details,
        metadata={
            "duration_days": duration_days,
            "assumed_uplift_pct": request.assumed_uplift_pct,
            "cost_breakdown": cost_breakdown,
            "budget_remaining": budget_remaining
        }
    )

