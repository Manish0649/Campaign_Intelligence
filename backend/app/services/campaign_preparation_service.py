"""Prepare decision candidates once and keep them in process memory."""

from datetime import datetime
from threading import RLock
from typing import Any, Dict, List

from backend.app.db.repositories.campaign_repo import CampaignRepository
from backend.app.db.session import SessionLocal

logger_name = "campaign_intelligence.preparation"

_cache_lock = RLock()
_prepared: Dict[str, Any] = {
    "status": "not_ready",
    "candidates": [],
    "skipped": [],
    "prepared_at": None,
}


def _build_candidate(campaign: dict, budget_data: dict) -> dict:
    """Keep the existing Decision Layer candidate calculations unchanged."""
    cid = campaign["campaign_id"]
    product_ids = campaign.get("target_product_ids", [])
    if isinstance(product_ids, str):
        product_ids = [p.strip() for p in product_ids.split(";") if p.strip()]

    # Budget status endpoint uses the same campaign date window and forecast source.
    # Its projected cost is reused here rather than making another HTTP request.
    total_forecast_units = float(budget_data.get("_total_forecast_units", 0.0))
    discount_rate = float(campaign.get("discount_rate", 0.15))
    uplift_pct = discount_rate * 1.5
    projected_units = total_forecast_units * (1.0 + uplift_pct)

    # Preserve the existing frontend's conservative fallback price and formulas.
    base_price = 5.0
    gross_revenue = projected_units * base_price * (1.0 - discount_rate)
    total_cost = budget_data.get(
        "total_projected_cost",
        float(campaign.get("campaign_budget", 0.0)) * 0.6,
    )
    expected_contribution = gross_revenue - total_cost

    projected_supply = int(projected_units * 1.2)
    net_usable_stock = max(0, projected_supply - int(total_forecast_units * 0.1))
    stock_coverage_ratio = round(projected_supply / max(1, projected_units), 2)
    stockout_risk_score = max(0.0, 1.0 - stock_coverage_ratio)

    budget_status = budget_data.get("budget_validation_status", "unknown")
    is_feasible = budget_status not in (
        "failed_budget_exceeded",
        "failed_zero_or_negative_budget",
    )
    feasibility_status = "feasible_for_review" if is_feasible else "infeasible"

    return {
        "campaign_id": cid,
        "campaign_name": campaign.get("campaign_name", cid),
        "campaign_type": campaign.get("campaign_type", "unknown"),
        "target_product_ids": product_ids,
        "target_segments": campaign.get("target_segments", "general"),
        "campaign_budget": float(campaign.get("campaign_budget", 0.0)),
        "discount_rate": discount_rate,
        "total_projected_cost": round(float(total_cost), 2),
        "projected_units": round(projected_units, 2),
        "gross_revenue": round(gross_revenue, 2),
        "expected_contribution": round(expected_contribution, 2),
        "projected_supply": projected_supply,
        "net_usable_stock": net_usable_stock,
        "stock_coverage_ratio": stock_coverage_ratio,
        "stockout_risk_score": round(stockout_risk_score, 4),
        "feasibility_status": feasibility_status,
        "is_feasible": is_feasible,
    }


def refresh_prepared_candidates() -> dict:
    """Rebuild candidates from current campaign, budget and forecast data."""
    import logging

    logger = logging.getLogger(logger_name)
    db = SessionLocal()
    candidates: List[dict] = []
    skipped: List[dict] = []
    try:
        # Import route helpers lazily to avoid coupling service initialization to
        # FastAPI router import order.
        from backend.app.api.routes.feasibility import get_campaign_budget_status
        from backend.app.api.routes.forecasts import forecast_repo

        campaigns = CampaignRepository(db).get_all_campaigns()
        for campaign in campaigns:
            campaign_id = campaign.get("campaign_id", "unknown")
            try:
                budget_model = get_campaign_budget_status(campaign_id, db)
                budget_data = budget_model.model_dump()

                # Reuse the forecast totals already represented by the budget
                # calculation. The repository's forecast cache avoids retraining.
                total_forecast_units = 0.0
                duration = (campaign["end_date"] - campaign["start_date"]).days + 1
                for product_id in campaign.get("target_product_ids", []):
                    forecast = forecast_repo.get_forecast(
                        product_id=product_id,
                        start_date=campaign["start_date"],
                        horizon_days=duration,
                    )
                    total_forecast_units += forecast.total_forecast_units
                budget_data["_total_forecast_units"] = total_forecast_units
                candidates.append(_build_candidate(campaign, budget_data))
            except Exception as exc:
                logger.exception("Candidate preparation failed for %s", campaign_id)
                skipped.append({"campaign_id": campaign_id, "reason": str(exc)})

        prepared = {
            "status": "ready" if candidates else "not_ready",
            "candidates": candidates,
            "skipped": skipped,
            "prepared_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        with _cache_lock:
            _prepared.update(prepared)
        logger.info(
            "Prepared %s decision candidates; skipped %s campaigns.",
            len(candidates), len(skipped),
        )
        return get_prepared_candidates()
    finally:
        db.close()


def get_prepared_candidates() -> dict:
    with _cache_lock:
        return {
            "status": _prepared["status"],
            "candidates": list(_prepared["candidates"]),
            "skipped": list(_prepared["skipped"]),
            "prepared_at": _prepared["prepared_at"],
            "total_candidates": len(_prepared["candidates"]),
        }
