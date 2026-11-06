from datetime import date
from typing import List, Literal

from fastapi import APIRouter, HTTPException, Query, Depends
from backend.app.security.auth import get_current_user

from backend.app.api.schemas.forecast import ForecastRequest, ProductForecastResponse
from backend.app.db.repositories.forecast_repo import (
    FORECAST_MODEL,
    ForecastDataError,
    ForecastNotFoundError,
    ForecastRepository,
)

router = APIRouter(tags=["Forecasting"], dependencies=[Depends(get_current_user)])
forecast_repo = ForecastRepository()


def _get_forecast_or_raise(product_id: str, start_date: date, horizon_days: int):
    try:
        return forecast_repo.get_forecast(
            product_id=product_id,
            start_date=start_date,
            horizon_days=horizon_days,
            model=FORECAST_MODEL,
        )
    except ForecastNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ForecastDataError as exc:
        raise HTTPException(
            status_code=503,
            detail="Forecast data is currently unavailable or invalid.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/forecasts/demand", response_model=List[ProductForecastResponse])
def get_demand_forecasts(request: ForecastRequest):
    """Retrieve linear-regression forecasts for every requested product."""
    return [
        _get_forecast_or_raise(
            product_id=product_id,
            start_date=request.start_date,
            horizon_days=request.horizon_days,
        )
        for product_id in request.product_ids
    ]


@router.get("/products/{product_id}/forecast", response_model=ProductForecastResponse)
def get_single_product_forecast(
    product_id: str,
    start_date: date = Query(...),
    horizon_days: int = Query(7, ge=1, le=30),
    model: Literal["linear_regression"] = Query(FORECAST_MODEL),
):
    """Retrieve a product's linear-regression forecast for an explicit date window."""
    return _get_forecast_or_raise(
        product_id=product_id,
        start_date=start_date,
        horizon_days=horizon_days,
    )
