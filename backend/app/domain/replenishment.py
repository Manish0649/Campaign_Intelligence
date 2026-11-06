
from datetime import date, datetime
from typing import Optional, List, Dict, Any, Union


def _to_date(val: Union[date, datetime, str]) -> date:
    """Normalize date, datetime, or ISO string to datetime.date."""
    if isinstance(val, datetime):
        return val.date()

    if isinstance(val, date):
        return val

    if isinstance(val, str):
        return datetime.fromisoformat(
            val.replace("Z", "+00:00")
        ).date()

    raise TypeError(
        f"Cannot coerce object of type {type(val)} to datetime.date"
    )


def validate_supplier_and_replenishment(
    supplier_id: str,
    supplier_status: str,
    lead_time_days: Optional[int],
    minimum_order_quantity: int,
    replenishment_capacity: int,
    expected_replenishment_date: Union[date, datetime, str],
    campaign_start_date: Union[date, datetime, str],
    campaign_end_date: Optional[Union[date, datetime, str]] = None
) -> Dict[str, Any]:

    warnings: List[str] = []
    rejection_reasons: List[str] = []

    is_valid = True
    usable_replenishment_units = 0

    exp_date = _to_date(expected_replenishment_date)
    start_date = _to_date(campaign_start_date)
    end_date = (
        _to_date(campaign_end_date)
        if campaign_end_date is not None
        else None
    )

    # 1. Supplier status validation
    status_lower = (
        supplier_status.strip().lower()
        if supplier_status
        else "unknown"
    )

    if status_lower != "active":
        is_valid = False
        rejection_reasons.append(
            f"failed_supplier_unavailable: Supplier '{supplier_id}' "
            f"is '{status_lower}' (must be active)"
        )

    # 2. Lead time validation
    if lead_time_days is None or lead_time_days <= 0:
        is_valid = False
        rejection_reasons.append(
            f"rejected_missing_supplier_lead_time: Supplier "
            f"'{supplier_id}' has missing or non-positive lead time "
            f"({lead_time_days})"
        )

    # 3. MOQ validation
    if minimum_order_quantity <= 0:
        is_valid = False
        rejection_reasons.append(
            f"rejected_invalid_minimum_order_quantity: "
            f"MOQ must be positive, received {minimum_order_quantity}"
        )

    # 4. Replenishment capacity validation
    if replenishment_capacity < 0:
        invalid_capacity = replenishment_capacity
        replenishment_capacity = 0
        is_valid = False
        rejection_reasons.append(
            f"rejected_invalid_replenishment_capacity: "
            f"Capacity cannot be negative, received {invalid_capacity}"
        )

    elif (
        minimum_order_quantity > 0
        and replenishment_capacity < minimum_order_quantity
    ):
        is_valid = False
        rejection_reasons.append(
            f"rejected_capacity_below_moq: Replenishment capacity "
            f"({replenishment_capacity}) is below MOQ "
            f"({minimum_order_quantity})"
        )

    # 5. Replenishment timing validation
    if exp_date <= start_date:
        usable_replenishment_units = replenishment_capacity

    elif end_date and exp_date <= end_date:
        usable_replenishment_units = replenishment_capacity

        warnings.append(
            f"warning_replenishment_mid_campaign: Expected "
            f"replenishment ({exp_date}) arrives during campaign "
            f"({start_date} to {end_date})"
        )

    else:
        usable_replenishment_units = 0

        warnings.append(
            f"warning_replenishment_after_campaign: Expected "
            f"replenishment ({exp_date}) arrives after campaign ends "
            f"({end_date or start_date})"
        )

        is_valid = False
        rejection_reasons.append(
            f"failed_replenishment_timing: Replenishment "
            f"({exp_date}) arrives after promotional window ends"
        )

    if not is_valid:
        # Invalid suppliers must never contribute assumed supply to feasibility.
        usable_replenishment_units = 0

    return {
        "is_valid": is_valid,
        "supplier_status": status_lower,
        "lead_time_days": lead_time_days,
        "minimum_order_quantity": minimum_order_quantity,
        "usable_replenishment_units": usable_replenishment_units,
        "replenishment_capacity": replenishment_capacity,
        "expected_replenishment_date": exp_date,
        "warnings": warnings,
        "rejection_reasons": rejection_reasons
    }
