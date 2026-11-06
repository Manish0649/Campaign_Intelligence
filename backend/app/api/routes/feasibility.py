from fastapi import APIRouter, HTTPException, Depends
from backend.app.security.auth import get_current_user
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from math import isfinite

from backend.app.db.session import get_db
from backend.app.api.schemas.proposal import FeasibilityRequest, FeasibilityResponse
from backend.app.api.schemas.campaign import CampaignBudgetStatus, CampaignResponse
from backend.app.db.repositories.campaign_repo import CampaignRepository
from backend.app.db.repositories.inventory_repo import InventoryRepository
from backend.app.db.repositories.forecast_repo import (
    FORECAST_MODEL, ForecastDataError, ForecastNotFoundError, ForecastRepository
)
from backend.app.domain.feasibility import evaluate_campaign_feasibility
from backend.app.domain.budget import calculate_campaign_cost, validate_campaign_budget

router = APIRouter(tags=["Feasibility"], dependencies=[Depends(get_current_user)])

def get_valid_product_price(camp_repo, product_id: str) -> float:
    """
    Retrieve and validate the registered product price.
    Never use an assumed fallback price.
    """
    product = camp_repo.get_product(product_id)

    if not product:
        raise HTTPException(
            status_code=422,
            detail=f"Product metadata is unavailable for '{product_id}'."
        )

    try:
        base_price = float(product["base_price"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail=f"Valid base price is unavailable for product '{product_id}'."
        )

    if not isfinite(base_price) or base_price <= 0:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid base price configured for product '{product_id}'."
        )

    return base_price

@router.get("/campaigns", response_model=List[CampaignResponse])
def list_campaigns(db: Session = Depends(get_db)):
    """
    List all available candidate campaigns.
    """
    repo = CampaignRepository(db)
    return repo.get_all_campaigns()


@router.post("/campaigns/feasibility", response_model=FeasibilityResponse)
def check_campaign_feasibility(
    request: FeasibilityRequest,
    db: Session = Depends(get_db)
):
    """
    Evaluate deterministic campaign feasibility across:
    - Hard budget constraints
    - Baseline and scenario forecast demand
    - Physical inventory availability & dynamic safety stock
    - Supplier replenishment & arrival timing
    - Operational data freshness
    """
    camp_repo = CampaignRepository(db)
    inv_repo = InventoryRepository(db)
    fc_repo = ForecastRepository()

    # 1. Campaign must be registered.
    camp_data = camp_repo.get_campaign(request.campaign_id)

    if not camp_data:
        raise HTTPException(
            status_code=404,
            detail=f"Campaign '{request.campaign_id}' not found."
        )

    # 2. Requested products must exactly match the registered scope.
    registered_product_ids = camp_data["target_product_ids"]
    requested_product_ids = request.product_ids

    if (
        len(requested_product_ids) != len(registered_product_ids)
        or set(requested_product_ids) != set(registered_product_ids)
    ):
        raise HTTPException(
            status_code=400,
            detail="Requested product scope does not match registered campaign scope."
        )

    # 3. Dates are user-selected evaluation dates, not restricted to the
    # campaign's originally registered calendar window. ForecastRepository
    # validates that the requested dates are forecastable from historical data.

    # 4. Always use the registered campaign budget and discount rate.
    # Ignore any budget override supplied by the client.
    budget = camp_data["campaign_budget"]
    discount_rate = camp_data["discount_rate"]

    # 5. Retrieve cost assumptions only after campaign validation.
    try:
        cost_assumptions = camp_repo.get_cost_assumption(
            request.campaign_id
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=422,
            detail="Cost assumptions are not configured for this campaign."
        ) from exc

    # 6. Gather data for each target product.
    product_data: Dict[str, Dict[str, Any]] = {}
    duration_days = (
        request.end_date - request.start_date
    ).days + 1

    for pid in request.product_ids:
        prod_meta = camp_repo.get_product(pid) 
        base_price = get_valid_product_price(camp_repo, pid)

        inv_snap = inv_repo.get_inventory_snapshot(pid)
        supp_info = inv_repo.get_supplier_replenishment(pid)

        try:
            fc_res = fc_repo.get_forecast(
                product_id=pid,
                start_date=request.start_date,
                horizon_days=max(1, duration_days),
                model=FORECAST_MODEL,
            )
        except ForecastNotFoundError as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc)
            ) from exc
        except ForecastDataError as exc:
            raise HTTPException(
                status_code=503,
                detail="Forecast data is currently unavailable or invalid.",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc)
            ) from exc

        product_data[pid] = {
            "product_name": prod_meta.get("product_name", pid),
            "base_price": base_price,
            "inventory": inv_snap,
            "supplier": supp_info,
            "baseline_forecast": fc_res.total_forecast_units
        }

    # 7. Execute deterministic feasibility evaluation.
    response = evaluate_campaign_feasibility(
        request=request,
        campaign_budget=budget,
        discount_rate=discount_rate,
        cost_assumptions=cost_assumptions,
        product_data=product_data
    )

    return response


@router.get("/campaigns/{campaign_id}/budget", response_model=CampaignBudgetStatus)
def get_campaign_budget_status(
    campaign_id: str,
    db: Session = Depends(get_db)
):
    """
    Retrieve campaign budget allocation, projected cost, and remaining ceiling.
    """
    camp_repo = CampaignRepository(db)
    fc_repo = ForecastRepository()

    camp_data = camp_repo.get_campaign(campaign_id)
    if not camp_data:
        raise HTTPException(status_code=404, detail=f"Campaign '{campaign_id}' not found.")

    try:
        cost_assumptions = camp_repo.get_cost_assumption(campaign_id)
    except LookupError as exc:
        raise HTTPException(status_code=422, detail="Cost assumptions are not configured for this campaign.") from exc
    target_products = camp_data["target_product_ids"]

    # Sum estimated campaign units across target products
    total_units = 0.0
    weighted_price = 0.0
    for pid in target_products:
        base_price = get_valid_product_price(camp_repo, pid)      
        duration_days = (camp_data["end_date"] - camp_data["start_date"]).days + 1
        try:
            fc = fc_repo.get_forecast(
                product_id=pid,
                start_date=camp_data["start_date"],
                horizon_days=duration_days,
                model=FORECAST_MODEL,
            )
        except ForecastNotFoundError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ForecastDataError as exc:
            raise HTTPException(
                status_code=503,
                detail="Forecast data is currently unavailable or invalid.",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        uplift_units = fc.total_forecast_units * 1.20
        total_units += uplift_units
        weighted_price += base_price * uplift_units

    avg_price = (weighted_price / total_units) if total_units > 0 else 0.0

    total_cost, breakdown = calculate_campaign_cost(
        fixed_setup_cost=cost_assumptions.fixed_campaign_cost,
        target_audience_size=5000,
        cost_per_contact=cost_assumptions.cost_per_contact,
        projected_campaign_units=total_units,
        sell_price=avg_price,
        discount_rate=camp_data["discount_rate"],
        logistics_surcharge=cost_assumptions.logistics_cost_assumption
    )

    budget_limit = camp_data["campaign_budget"]
    is_ok, status, remaining = validate_campaign_budget(budget_limit, total_cost)

    return CampaignBudgetStatus(
        campaign_id=campaign_id,
        budget_limit=budget_limit,
        total_projected_cost=total_cost,
        budget_remaining=remaining,
        budget_validation_status=status,
        cost_breakdown=breakdown
    )

