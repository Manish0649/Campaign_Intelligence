import pytest
from datetime import date, datetime
from backend.app.api.schemas.proposal import FeasibilityRequest
from backend.app.api.schemas.campaign import CampaignCostAssumption
from backend.app.domain.feasibility import evaluate_campaign_feasibility

@pytest.fixture
def base_cost_assumption():
    return CampaignCostAssumption(
        campaign_id="CAMP-TEST",
        fixed_campaign_cost=800.0,
        cost_per_contact=0.08,
        discount_cost_assumption="retailer_absorbed",
        logistics_cost_assumption=1.20
    )

def test_feasibility_engine_fully_feasible(base_cost_assumption):
    req = FeasibilityRequest(
        campaign_id="CAMP-TEST",
        product_ids=["PROD_A"],
        start_date=date(2016, 4, 25),
        end_date=date(2016, 5, 1),
        budget_limit=5000.0,
        assumed_uplift_pct=0.20
    )

    product_data = {
        "PROD_A": {
            "product_name": "Test Product A",
            "base_price": 8.0,
            "baseline_forecast": 10.0,  # +20% uplift = 12 units
            "inventory": {
                "on_hand_stock": 50,
                "reserved_stock": 5,
                "safety_stock": 10,
                "inventory_updated_at": datetime(2016, 4, 24, 12, 0)
            },
            "supplier": {
                "supplier_id": "SUPP_1",
                "supplier_status": "active",
                "lead_time_days": 3,
                "minimum_order_quantity": 20,
                "replenishment_capacity": 50,
                "expected_replenishment_date": date(2016, 4, 24)
            }
        }
    }

    res = evaluate_campaign_feasibility(
        request=req,
        campaign_budget=5000.0,
        discount_rate=0.15,
        cost_assumptions=base_cost_assumption,
        product_data=product_data,
        evaluation_time=datetime(2016, 4, 25, 0, 0)
    )

    assert res.status == "feasible_for_review"
    assert res.budget_validation == "passed"
    assert res.inventory_validation == "passed"
    assert res.replenishment_validation == "passed"
    assert len(res.rejection_reasons) == 0

def test_feasibility_engine_stockout_rejection(base_cost_assumption):
    req = FeasibilityRequest(
        campaign_id="CAMP-TEST",
        product_ids=["PROD_LOW"],
        start_date=date(2016, 4, 25),
        end_date=date(2016, 5, 1),
        budget_limit=5000.0,
        assumed_uplift_pct=0.20
    )

    product_data = {
        "PROD_LOW": {
            "product_name": "Low Stock Product",
            "base_price": 10.0,
            "baseline_forecast": 30.0,  # 30 * 1.2 = 36 units required
            "inventory": {
                "on_hand_stock": 15,
                "reserved_stock": 5,
                "safety_stock": 5,  # net usable = 5
                "inventory_updated_at": datetime(2016, 4, 24, 12, 0)
            },
            "supplier": None  # No replenishment
        }
    }

    res = evaluate_campaign_feasibility(
        request=req,
        campaign_budget=5000.0,
        discount_rate=0.15,
        cost_assumptions=base_cost_assumption,
        product_data=product_data,
        evaluation_time=datetime(2016, 4, 25, 0, 0)
    )

    assert res.status == "rejected_by_policy"
    assert res.inventory_validation == "failed"
    assert any("failed_insufficient_stock" in r for r in res.rejection_reasons)

def test_feasibility_engine_budget_rejection(base_cost_assumption):
    req = FeasibilityRequest(
        campaign_id="CAMP-TEST",
        product_ids=["PROD_A"],
        start_date=date(2016, 4, 25),
        end_date=date(2016, 5, 1),
        budget_limit=500.0,  # tiny budget limit < fixed cost of 800
        assumed_uplift_pct=0.20
    )

    product_data = {
        "PROD_A": {
            "product_name": "Test Product A",
            "base_price": 8.0,
            "baseline_forecast": 10.0,
            "inventory": {
                "on_hand_stock": 50,
                "reserved_stock": 5,
                "safety_stock": 10,
                "inventory_updated_at": datetime(2016, 4, 24, 12, 0)
            },
            "supplier": {
                "supplier_id": "SUPP_1",
                "supplier_status": "active",
                "lead_time_days": 3,
                "minimum_order_quantity": 20,
                "replenishment_capacity": 50,
                "expected_replenishment_date": date(2016, 4, 24)
            }
        }
    }

    res = evaluate_campaign_feasibility(
        request=req,
        campaign_budget=500.0,
        discount_rate=0.15,
        cost_assumptions=base_cost_assumption,
        product_data=product_data
    )

    assert res.status == "rejected_by_policy"
    assert res.budget_validation == "failed"
    assert any("failed_budget_exceeded" in r for r in res.rejection_reasons)



def test_feasibility_rejects_missing_baseline_forecast(base_cost_assumption):
    req = FeasibilityRequest(
        campaign_id="CAMP-TEST",
        product_ids=["PROD_NO_FORECAST"],
        start_date=date(2016, 4, 25),
        end_date=date(2016, 5, 1),
        budget_limit=5000.0,
    )
    product_data = {
        "PROD_NO_FORECAST": {
            "product_name": "Product without forecast",
            "base_price": 8.0,
            "inventory": {
                "on_hand_stock": 50,
                "reserved_stock": 5,
                "safety_stock": 10,
                "inventory_updated_at": datetime(2016, 4, 24, 12, 0),
            },
            "supplier": None,
        }
    }

    result = evaluate_campaign_feasibility(
        request=req,
        campaign_budget=5000.0,
        discount_rate=0.15,
        cost_assumptions=base_cost_assumption,
        product_data=product_data,
        evaluation_time=datetime(2016, 4, 25, 0, 0),
    )

    assert result.status == "rejected_by_policy"
    assert result.forecast_validation == "failed"
    assert any(
        "rejected_missing_or_invalid_forecast" in reason
        for reason in result.rejection_reasons
    )
    assert result.product_details == []


def test_feasibility_rejects_missing_or_invalid_base_price(base_cost_assumption):
    req = FeasibilityRequest(
        campaign_id="CAMP-TEST",
        product_ids=["PROD_NO_PRICE"],
        start_date=date(2016, 4, 25),
        end_date=date(2016, 5, 1),
    )
    product_data = {
        "PROD_NO_PRICE": {
            "product_name": "Product without a registered price",
            "baseline_forecast": 10.0,
            "inventory": {
                "on_hand_stock": 100,
                "reserved_stock": 0,
                "safety_stock": 10,
                "inventory_updated_at": datetime(2016, 4, 24, 12, 0),
            },
            "supplier": {
                "supplier_id": "SUPP-PRICE",
                "supplier_status": "active",
                "lead_time_days": 4,
                "minimum_order_quantity": 10,
                "replenishment_capacity": 100,
                "expected_replenishment_date": date(2016, 4, 24),
            },
        }
    }
    result = evaluate_campaign_feasibility(
        request=req,
        campaign_budget=5000.0,
        discount_rate=0.10,
        cost_assumptions=base_cost_assumption,
        product_data=product_data,
        evaluation_time=datetime(2016, 4, 25),
    )
    assert result.status == "rejected_by_policy"
    assert any("rejected_missing_or_invalid_product_price" in reason for reason in result.rejection_reasons)
