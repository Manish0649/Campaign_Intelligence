from typing import Dict, Any, Tuple
from backend.app.api.schemas.campaign import CampaignCostAssumption

def calculate_campaign_cost(
    fixed_setup_cost: float,
    target_audience_size: int,
    cost_per_contact: float,
    projected_campaign_units: float,
    sell_price: float,
    discount_rate: float,
    logistics_surcharge: float,
    discount_cost_assumption: str = "retailer_absorbed"
) -> Tuple[float, Dict[str, float]]:
    """
    Calculates total projected campaign cost using:
    Total Cost = Fixed Setup Cost + (Audience * Cost per Contact) + 
                 (Projected Units * Sell Price * Discount Rate) + 
                 (Projected Units * Logistics Surcharge)
    """
    setup_cost = float(fixed_setup_cost)
    contact_cost = float(target_audience_size) * float(cost_per_contact)
    
    # If vendor co-funded, discount cost is not absorbed by retailer
    if discount_cost_assumption == "vendor_co_funded":
        discount_cost = 0.0
    else:
        discount_cost = float(projected_campaign_units) * float(sell_price) * float(discount_rate)
        
    logistics_cost = float(projected_campaign_units) * float(logistics_surcharge)
    
    total_cost = setup_cost + contact_cost + discount_cost + logistics_cost
    
    breakdown = {
        "fixed_setup_cost": round(setup_cost, 2),
        "contact_outreach_cost": round(contact_cost, 2),
        "discount_markdown_cost": round(discount_cost, 2),
        "logistics_surcharge_cost": round(logistics_cost, 2),
        "total_projected_cost": round(total_cost, 2)
    }
    return round(total_cost, 2), breakdown

def validate_campaign_budget(
    campaign_budget: float,
    total_projected_cost: float
) -> Tuple[bool, str, float]:
    """
    Hard Budget Constraint (Rule 2):
    Under no circumstances can a campaign be approved if total projected cost exceeds the budget limit.
    Campaign budget must be strictly positive (> 0.0).
    """
    campaign_budget = float(campaign_budget)
    total_projected_cost = float(total_projected_cost)
    
    if campaign_budget <= 0.0:
        return False, "failed_zero_or_negative_budget", round(-total_projected_cost, 2)
        
    budget_remaining = round(campaign_budget - total_projected_cost, 2)
    if total_projected_cost > campaign_budget:
        return False, "failed_budget_exceeded", budget_remaining
    return True, "passed", budget_remaining

