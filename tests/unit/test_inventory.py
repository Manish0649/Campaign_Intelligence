import pytest
from datetime import datetime, timedelta
from backend.app.domain.inventory import (
    calculate_dynamic_safety_stock, validate_inventory_availability
)

def test_calculate_dynamic_safety_stock():
    # Z=1.65, L=4, sigma=2.0 -> 1.65 * 2 * 2.0 = 6.6 -> ceil(6.6) = 7
    ss = calculate_dynamic_safety_stock(z_score=1.65, lead_time_days=4, daily_sales_std=2.0)
    assert ss == 7

def test_inventory_availability_passed():
    eval_result = validate_inventory_availability(
        on_hand_stock=50,
        reserved_stock=10,
        safety_stock=15,
        snapshot_timestamp=datetime(2016, 4, 24, 12, 0, 0),
        reference_time=datetime(2016, 4, 25, 0, 0, 0)
    )
    assert eval_result["status"] == "passed"
    assert eval_result["net_usable_stock"] == 25  # 50 - 10 - 15
    assert len(eval_result["warnings"]) == 0
    assert len(eval_result["rejection_reasons"]) == 0

def test_inventory_safety_stock_breach():
    # on_hand=20, reserved=10 -> effective available=10 < safety_stock=15
    eval_result = validate_inventory_availability(
        on_hand_stock=20,
        reserved_stock=10,
        safety_stock=15,
        snapshot_timestamp=datetime(2016, 4, 24, 12, 0, 0),
        reference_time=datetime(2016, 4, 25, 0, 0, 0)
    )
    assert eval_result["status"] == "failed_safety_stock_breach"
    assert any("rejected_safety_stock_violation" in r for r in eval_result["rejection_reasons"])

def test_inventory_stale_data_warning():
    # Snapshot older than 72 hours (4 days old)
    old_timestamp = datetime(2016, 4, 20, 0, 0, 0)
    ref_time = datetime(2016, 4, 25, 0, 0, 0)
    eval_result = validate_inventory_availability(
        on_hand_stock=100,
        reserved_stock=15,
        safety_stock=20,
        snapshot_timestamp=old_timestamp,
        reference_time=ref_time,
        staleness_hours_limit=72
    )
    assert eval_result["status"] == "passed"
    assert any("warning_stale_inventory" in w for w in eval_result["warnings"])



def test_negative_inventory_values_are_rejected_fail_closed():
    result = validate_inventory_availability(
        on_hand_stock=-5,
        reserved_stock=0,
        safety_stock=10,
    )
    assert result["status"] == "failed_invalid_inventory_data"
    assert result["net_usable_stock"] == 0
    assert any("rejected_invalid_inventory_values" in reason for reason in result["rejection_reasons"])
