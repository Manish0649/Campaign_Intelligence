
from datetime import date

import pytest

from backend.app.domain.replenishment import (
    validate_supplier_and_replenishment,
)


def get_valid_input(**overrides):
    data = {
        "supplier_id": "SUP-001",
        "supplier_status": "active",
        "lead_time_days": 5,
        "minimum_order_quantity": 50,
        "replenishment_capacity": 200,
        "expected_replenishment_date": date(2026, 11, 1),
        "campaign_start_date": date(2026, 11, 5),
        "campaign_end_date": date(2026, 11, 15),
    }

    data.update(overrides)
    return data


def test_valid_replenishment():
    result = validate_supplier_and_replenishment(
        **get_valid_input()
    )

    assert result["is_valid"] is True
    assert result["usable_replenishment_units"] == 200


@pytest.mark.parametrize(
    ("overrides", "expected_reason"),
    [
        (
            {"minimum_order_quantity": 0},
            "rejected_invalid_minimum_order_quantity",
        ),
        (
            {"minimum_order_quantity": -10},
            "rejected_invalid_minimum_order_quantity",
        ),
        (
            {"replenishment_capacity": -10},
            "rejected_invalid_replenishment_capacity",
        ),
        (
            {
                "minimum_order_quantity": 100,
                "replenishment_capacity": 50,
            },
            "rejected_capacity_below_moq",
        ),
    ],
)
def test_invalid_replenishment_values(overrides, expected_reason):
    result = validate_supplier_and_replenishment(
        **get_valid_input(**overrides)
    )

    assert result["is_valid"] is False
    assert any(
        expected_reason in reason
        for reason in result["rejection_reasons"]
    )


def test_replenishment_after_campaign():
    result = validate_supplier_and_replenishment(
        **get_valid_input(
            expected_replenishment_date=date(2026, 11, 20)
        )
    )

    assert result["is_valid"] is False
    assert result["usable_replenishment_units"] == 0
    assert any(
        "failed_replenishment_timing" in reason
        for reason in result["rejection_reasons"]
    )


def test_invalid_supplier_never_contributes_replenishment_units():
    result = validate_supplier_and_replenishment(
        supplier_id="SUPP-SUSPENDED",
        supplier_status="suspended",
        lead_time_days=4,
        minimum_order_quantity=20,
        replenishment_capacity=200,
        expected_replenishment_date=date(2016, 4, 24),
        campaign_start_date=date(2016, 4, 25),
        campaign_end_date=date(2016, 5, 1),
    )
    assert result["is_valid"] is False
    assert result["usable_replenishment_units"] == 0
    assert any("failed_supplier_unavailable" in reason for reason in result["rejection_reasons"])
