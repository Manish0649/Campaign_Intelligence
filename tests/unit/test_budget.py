import pytest
from backend.app.domain.budget import calculate_campaign_cost, validate_campaign_budget

def test_calculate_campaign_cost_retailer_absorbed():
    total_cost, breakdown = calculate_campaign_cost(
        fixed_setup_cost=800.0,
        target_audience_size=5000,
        cost_per_contact=0.08,
        projected_campaign_units=100.0,
        sell_price=10.0,
        discount_rate=0.15,
        logistics_surcharge=1.20,
        discount_cost_assumption="retailer_absorbed"
    )
    # 800 + (5000 * 0.08 = 400) + (100 * 10 * 0.15 = 150) + (100 * 1.20 = 120) = 1470.0
    assert total_cost == 1470.0
    assert breakdown["fixed_setup_cost"] == 800.0
    assert breakdown["contact_outreach_cost"] == 400.0
    assert breakdown["discount_markdown_cost"] == 150.0
    assert breakdown["logistics_surcharge_cost"] == 120.0

def test_calculate_campaign_cost_vendor_co_funded():
    total_cost, breakdown = calculate_campaign_cost(
        fixed_setup_cost=500.0,
        target_audience_size=1000,
        cost_per_contact=0.10,
        projected_campaign_units=50.0,
        sell_price=20.0,
        discount_rate=0.20,
        logistics_surcharge=2.00,
        discount_cost_assumption="vendor_co_funded"
    )
    # 500 + 100 + 0 + 100 = 700.0
    assert total_cost == 700.0
    assert breakdown["discount_markdown_cost"] == 0.0

def test_validate_campaign_budget_sufficient():
    passed, status, remaining = validate_campaign_budget(
        campaign_budget=5000.0,
        total_projected_cost=3200.0
    )
    assert passed is True
    assert status == "passed"
    assert remaining == 1800.0

def test_validate_campaign_budget_exceeded():
    passed, status, remaining = validate_campaign_budget(
        campaign_budget=2000.0,
        total_projected_cost=2500.0
    )
    assert passed is False
    assert status == "failed_budget_exceeded"
    assert remaining == -500.0

