from datetime import date
from typing import List, Literal

from pydantic import BaseModel, Field


class ForecastRequest(BaseModel):
    product_ids: List[str] = Field(..., min_length=1)
    start_date: date
    horizon_days: int = Field(default=7, ge=1, le=30)
    model: Literal["linear_regression"] = "linear_regression"


class ForecastPoint(BaseModel):
    date: date
    forecast_units: float


class ProductForecastResponse(BaseModel):
    product_id: str
    model: str
    forecast_version: str = "m5-dynamic-linear-v2"
    horizon_days: int
    total_forecast_units: float
    daily_forecasts: List[ForecastPoint]
