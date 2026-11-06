from datetime import date, datetime, timedelta
from math import isfinite
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from backend.app.config import settings
from backend.app.api.schemas.forecast import ProductForecastResponse, ForecastPoint

FORECAST_MODEL = "linear_regression"
FORECAST_VERSION = "m5-dynamic-linear-v2"
MAX_FORECAST_HORIZON_DAYS = 30
MAX_FORECAST_LEAD_DAYS = 7300


class ForecastNotFoundError(LookupError):
    """Raised when historical demand for a requested product is unavailable."""


class ForecastDataError(RuntimeError):
    """Raised when the historical forecast source is missing or invalid."""


class ForecastRepository:
    """Build forecasts on demand from historical sales, not fixed calendar rows."""

    def __init__(self):
        self.history_file = settings.processed_dir.parent / "m5_processed_features.csv"
        self._cached_df: Optional[pd.DataFrame] = None

    def _load_history(self) -> pd.DataFrame:
        if self._cached_df is not None:
            return self._cached_df
        if not self.history_file.is_file():
            raise ForecastDataError(
                f"Historical demand file is unavailable: {self.history_file.name}"
            )
        try:
            df = pd.read_csv(self.history_file, usecols=["product_id", "date", "sales_units"])
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            raise ForecastDataError("Historical demand data could not be read.") from exc
        if df.empty:
            raise ForecastDataError("Historical demand data contains no rows.")
        df["product_id"] = df["product_id"].astype(str).str.strip()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["sales_units"] = pd.to_numeric(df["sales_units"], errors="coerce")
        if df[["date", "sales_units"]].isna().any().any():
            raise ForecastDataError("Historical demand contains invalid dates or values.")
        if (df["sales_units"] < 0).any() or not np.isfinite(df["sales_units"]).all():
            raise ForecastDataError("Historical demand contains negative or non-finite values.")
        # Aggregate across stores if product_id is represented in multiple stores.
        daily = (df.groupby(["product_id", "date"], as_index=False)["sales_units"]
                   .sum().sort_values(["product_id", "date"]))
        self._cached_df = daily
        return daily

    @staticmethod
    def _features(day: date, history: list[float], origin: date) -> list[float]:
        dow = day.weekday()
        doy = day.timetuple().tm_yday
        recent = history[-28:]
        return [
            float((day - origin).days),
            float(dow),
            float(np.sin(2 * np.pi * dow / 7)),
            float(np.cos(2 * np.pi * dow / 7)),
            float(day.month),
            float(np.sin(2 * np.pi * doy / 365.25)),
            float(np.cos(2 * np.pi * doy / 365.25)),
            float(history[-7]) if len(history) >= 7 else float(history[-1]),
            float(history[-14]) if len(history) >= 14 else float(history[-1]),
            float(history[-28]) if len(history) >= 28 else float(history[-1]),
            float(np.mean(history[-7:])),
            float(np.mean(recent)),
            float(np.std(recent)),
        ]

    def _forecast_series(self, series: pd.DataFrame, requested_dates: list[date]) -> list[float]:
        series = series.sort_values("date")
        origin = series["date"].max().date()

        # Every requested date must be strictly after historical origin.
        if not requested_dates or min(requested_dates) <= origin:
            raise ValueError(
                f"Forecast dates must be after the latest historical date ({origin.isoformat()})."
            )

        last_requested = max(requested_dates)
        lead_days = (last_requested - origin).days

        if lead_days > MAX_FORECAST_LEAD_DAYS:
            raise ValueError(
                f"Forecast start date is too far ahead; maximum lead is {MAX_FORECAST_LEAD_DAYS} days."
            )

        demand = series["sales_units"].astype(float).tolist()
        if len(demand) < 28:
            raise ForecastDataError("At least 28 days of historical demand are required.")
        # Train a per-product model with calendar, lag and rolling-demand features.
        x_rows, y_rows = [], []
        dates = [stamp.date() for stamp in series["date"]]
        for idx in range(28, len(demand)):
            x_rows.append(self._features(dates[idx], demand[:idx], origin))
            y_rows.append(demand[idx])
        model = LinearRegression()
        model.fit(np.asarray(x_rows, dtype=float), np.asarray(y_rows, dtype=float))

        # Preserve weekday seasonality so forecasts do not repeat one scalar value.
        recent_history = series.tail(56).copy()
        recent_history["weekday"] = recent_history["date"].dt.weekday
        weekday_profile = recent_history.groupby("weekday")["sales_units"].mean().to_dict()

        wanted = set(requested_dates)
        results = {}
        for offset in range(1, lead_days + 1):
            day = origin + timedelta(days=offset)
            features = np.asarray([self._features(day, demand, origin)], dtype=float)
            regression_prediction = float(model.predict(features)[0])
            weekday_average = float(weekday_profile.get(day.weekday(), demand[-1]))
            prediction = max(0.0, 0.60 * regression_prediction + 0.40 * weekday_average)
            results[day] = prediction
            demand.append(prediction)
        return [round(results[day], 2) for day in requested_dates]

    def get_forecast(
        self,
        product_id: str,
        start_date: date,
        horizon_days: int = 7,
        model: str = FORECAST_MODEL,
    ) -> ProductForecastResponse:
        if not product_id or not product_id.strip():
            raise ValueError("product_id must be a non-empty string.")
        product_id = product_id.strip()
        if isinstance(start_date, datetime):
            start_date = start_date.date()
        if not isinstance(start_date, date):
            raise ValueError("start_date must be supplied as a date.")
        if horizon_days < 1 or horizon_days > MAX_FORECAST_HORIZON_DAYS:
            raise ValueError(f"horizon_days must be between 1 and {MAX_FORECAST_HORIZON_DAYS}.")
        if model != FORECAST_MODEL:
            raise ValueError(f"Unsupported forecast model '{model}'. Use '{FORECAST_MODEL}'.")

        df = self._load_history()
        product_rows = df[df["product_id"] == product_id]
        if product_rows.empty:
            raise ForecastNotFoundError(f"No historical demand is available for product '{product_id}'.")
        requested_dates = [start_date + timedelta(days=offset) for offset in range(horizon_days)]
        forecasts = self._forecast_series(product_rows, requested_dates)
        daily_points = [
            ForecastPoint(date=day, forecast_units=value)
            for day, value in zip(requested_dates, forecasts)
        ]
        return ProductForecastResponse(
            product_id=product_id,
            model=model,
            forecast_version=FORECAST_VERSION,
            horizon_days=len(daily_points),
            total_forecast_units=round(sum(forecasts), 2),
            daily_forecasts=daily_points,
        )
