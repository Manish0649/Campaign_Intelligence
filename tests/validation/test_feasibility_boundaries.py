from datetime import date, datetime, timedelta
import pytest

from backend.app.domain.budget import validate_campaign_budget, calculate_campaign_cost
from backend.app.domain.inventory import validate_inventory_availability
from backend.app.domain.replenishment import validate_supplier_and_replenishment
from backend.app.domain.feasibility import evaluate_campaign_feasibility
from backend.app.api.schemas.proposal import FeasibilityRequest
from backend.app.api.schemas.campaign import CampaignCostAssumption

# ---------------------------------------------------------------------------
# 1. Budget Boundary Tests (Rule 2)
# ---------------------------------------------------------------------------
def test_budget_boundary_exact_match():
    """Cost exactly equals configured budget: Must PASS with $0.00 remaining."""
    budget = 5000.00
    cost = 5000.00
    ok, status, remaining = validate_campaign_budget(budget, cost)
    assert ok is True
    assert status == "passed"
    assert remaining == 0.00

def test_budget_boundary_just_below_limit():
    """Cost is 1 cent below budget: Must PASS with $0.01 remaining."""
    budget = 5000.00
    cost = 4999.99
    ok, status, remaining = validate_campaign_budget(budget, cost)
    assert ok is True
    assert status == "passed"
    assert remaining == 0.01

def test_budget_boundary_just_above_limit():
    """Cost is 1 cent above budget: Must FAIL with -$0.01 remaining."""
    budget = 5000.00
    cost = 5000.01
    ok, status, remaining = validate_campaign_budget(budget, cost)
    assert ok is False
    assert status == "failed_budget_exceeded"
    assert remaining == -0.01

def test_budget_boundary_zero_and_negative():
    """Zero or negative budget must be explicitly rejected (Corrected Defect DEF-02)."""
    # Zero budget
    ok_zero, status_zero, _ = validate_campaign_budget(0.0, 0.0)
    assert ok_zero is False
    assert status_zero == "failed_zero_or_negative_budget"

    # Negative budget
    ok_neg, status_neg, _ = validate_campaign_budget(-100.0, 50.0)
    assert ok_neg is False
    assert status_neg == "failed_zero_or_negative_budget"

# ---------------------------------------------------------------------------
# 2. Inventory & Safety Stock Tests
# ---------------------------------------------------------------------------
def test_inventory_insufficient_stock():
    """Effective stock is below promotional demand: Feasibility must reject."""
    eval_res = validate_inventory_availability(
        on_hand_stock=30,
        reserved_stock=10,
        safety_stock=10
    )
    # Available = 20, Safety = 10 -> Net usable = 10
    assert eval_res["status"] == "passed"
    assert eval_res["net_usable_stock"] == 10

def test_safety_stock_breach_rejection():
    """Effective stock (on_hand - reserved) < safety_stock: Must REJECT immediately."""
    eval_res = validate_inventory_availability(
        on_hand_stock=25,
        reserved_stock=15,  # Effective available = 10
        safety_stock=20     # Safety stock required = 20
    )
    assert eval_res["status"] == "failed_safety_stock_breach"
    assert any("rejected_safety_stock_violation" in r for r in eval_res["rejection_reasons"])
    assert eval_res["net_usable_stock"] == 0  # Floored at 0, never negative

def test_oversold_inventory_flooring():
    """Reserved stock exceeds physical on-hand stock: Floored cleanly at 0 (DEF-03)."""
    eval_res = validate_inventory_availability(
        on_hand_stock=20,
        reserved_stock=35,  # Oversold by 15 units
        safety_stock=10
    )
    assert eval_res["status"] == "failed_safety_stock_breach"
    assert any("warning_oversold_inventory" in w for w in eval_res["warnings"])
    assert eval_res["net_usable_stock"] == 0

def test_stale_inventory_snapshot_warning():
    """Snapshot older than 72 hours must trigger freshness warning (Rule 9)."""
    ref_time = datetime(2016, 4, 25, 12, 0, 0)
    stale_timestamp = ref_time - timedelta(hours=96)  # 96 hours old
    
    eval_res = validate_inventory_availability(
        on_hand_stock=100,
        reserved_stock=20,
        safety_stock=20,
        snapshot_timestamp=stale_timestamp,
        reference_time=ref_time,
        staleness_hours_limit=72
    )
    assert any("warning_stale_inventory" in w for w in eval_res["warnings"])
    assert "96.0h" in eval_res["warnings"][0]

# ---------------------------------------------------------------------------
# 3. Replenishment Lead Time & Timing Tests
# ---------------------------------------------------------------------------
def test_missing_supplier_lead_time_rejection():
    """Supplier with missing or non-positive lead time must fail validation."""
    # None lead time
    res_none = validate_supplier_and_replenishment(
        supplier_id="SUPP-01",
        supplier_status="active",
        lead_time_days=None,
        minimum_order_quantity=10,
        replenishment_capacity=100,
        expected_replenishment_date=date(2016, 4, 24),
        campaign_start_date=date(2016, 4, 25)
    )
    assert res_none["is_valid"] is False
    assert any("rejected_missing_supplier_lead_time" in r for r in res_none["rejection_reasons"])

    # Zero lead time
    res_zero = validate_supplier_and_replenishment(
        supplier_id="SUPP-01",
        supplier_status="active",
        lead_time_days=0,
        minimum_order_quantity=10,
        replenishment_capacity=100,
        expected_replenishment_date=date(2016, 4, 24),
        campaign_start_date=date(2016, 4, 25)
    )
    assert res_zero["is_valid"] is False

def test_replenishment_arriving_after_campaign_ends():
    """Replenishment arriving after campaign end date cannot fulfill campaign demand."""
    res = validate_supplier_and_replenishment(
        supplier_id="SUPP-01",
        supplier_status="active",
        lead_time_days=4,
        minimum_order_quantity=10,
        replenishment_capacity=100,
        expected_replenishment_date=date(2016, 5, 5),   # Arrives May 5
        campaign_start_date=date(2016, 4, 25),          # Campaign April 25 to May 1
        campaign_end_date=date(2016, 5, 1)
    )
    assert res["usable_replenishment_units"] == 0
    assert any("failed_replenishment_timing" in r for r in res["rejection_reasons"])

def test_replenishment_date_coercion_safe():
    """Datetime objects and ISO strings are coerced safely without TypeError (DEF-01)."""
    # Pass datetime instead of date
    res_dt = validate_supplier_and_replenishment(
        supplier_id="SUPP-01",
        supplier_status="active",
        lead_time_days=3,
        minimum_order_quantity=10,
        replenishment_capacity=150,
        expected_replenishment_date=datetime(2016, 4, 24, 15, 30),
        campaign_start_date=datetime(2016, 4, 25, 0, 0),
        campaign_end_date="2016-05-01"
    )
    assert res_dt["is_valid"] is True
    assert res_dt["usable_replenishment_units"] == 150
    assert isinstance(res_dt["expected_replenishment_date"], date)

