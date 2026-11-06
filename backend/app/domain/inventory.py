import math
from datetime import datetime, timezone
from typing import Optional, Tuple, List, Dict, Any

def calculate_dynamic_safety_stock(
    z_score: float = 1.65,
    lead_time_days: int = 3,
    daily_sales_std: float = 2.0
) -> int:
    """
    Safety Stock = ceil(Z * sqrt(L) * sigma_daily)
    Z = 1.65 (95% service level)
    L = Supplier Lead Time in days
    sigma_daily = Standard deviation of daily sales over trailing 30 days
    """
    if lead_time_days <= 0 or daily_sales_std <= 0:
        return 0
    return math.ceil(z_score * math.sqrt(lead_time_days) * daily_sales_std)

def validate_inventory_availability(
    on_hand_stock: int,
    reserved_stock: int,
    safety_stock: int,
    snapshot_timestamp: Optional[datetime] = None,
    reference_time: Optional[datetime] = None,
    staleness_hours_limit: int = 72
) -> Dict[str, Any]:
    """
    Evaluates net usable stock, safety stock compliance, and snapshot staleness.
    Rule 9: Flag missing or stale operational data.
    """
    warnings: List[str] = []
    rejection_reasons: List[str] = []

    if on_hand_stock < 0 or reserved_stock < 0 or safety_stock < 0:
        rejection_reasons.append(
            "rejected_invalid_inventory_values: On-hand, reserved and safety stock values must be non-negative."
        )
        on_hand_stock = max(0, on_hand_stock)
        reserved_stock = max(0, reserved_stock)
        safety_stock = max(0, safety_stock)
    
    # 1. Staleness check
    if snapshot_timestamp:
        # Standardize naive datetimes
        ref = reference_time or datetime.now(timezone.utc)
        # remove tzinfo if present for simple diff
        st_naive = (
            snapshot_timestamp.astimezone(timezone.utc).replace(tzinfo=None)
            if snapshot_timestamp.tzinfo
            else snapshot_timestamp
        )
        ref_naive = (
            ref.astimezone(timezone.utc).replace(tzinfo=None)
            if ref.tzinfo
            else ref
        )
        
        diff_hours = (ref_naive - st_naive).total_seconds() / 3600.0
        if diff_hours > staleness_hours_limit:
            warnings.append(
                f"warning_stale_inventory: Snapshot age ({diff_hours:.1f}h) exceeds freshness threshold ({staleness_hours_limit}h)"
            )
            
    # 2. Safety stock and inventory boundary checks
    if reserved_stock > on_hand_stock:
        warnings.append(
            f"warning_oversold_inventory: Reserved stock ({reserved_stock}) exceeds physical on-hand stock ({on_hand_stock})"
        )

    effective_available = max(0, on_hand_stock - reserved_stock)
    net_usable_stock = max(0, effective_available - safety_stock)
    
    if rejection_reasons:
        status = "failed_invalid_inventory_data"
    elif (on_hand_stock - reserved_stock) < safety_stock:
        status = "failed_safety_stock_breach"
        rejection_reasons.append(
            f"rejected_safety_stock_violation: Effective available stock ({on_hand_stock - reserved_stock}) is below mandatory safety stock ({safety_stock})"
        )
    else:
        status = "passed"
        
    return {
        "status": status,
        "on_hand_stock": on_hand_stock,
        "reserved_stock": reserved_stock,
        "safety_stock": safety_stock,
        "net_usable_stock": net_usable_stock,
        "warnings": warnings,
        "rejection_reasons": rejection_reasons
    }

