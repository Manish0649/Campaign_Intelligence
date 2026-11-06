from tests.auth_helpers import auth_headers
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app, headers=auth_headers())

def test_single_product_forecast():
    response = client.get("/products/FOODS_1_018/forecast?start_date=2026-11-07&horizon_days=7")
    assert response.status_code == 200
    data = response.json()
    assert data["product_id"] == "FOODS_1_018"
    assert data["model"] == "linear_regression"
    assert data["horizon_days"] == 7
    assert data["total_forecast_units"] >= 0
    assert len(data["daily_forecasts"]) == 7

def test_demand_forecast_batch():
    payload = {
        "product_ids": ["FOODS_1_018", "FOODS_1_019"],
        "start_date": "2026-11-07",
        "horizon_days": 7,
        "model": "linear_regression"
    }
    response = client.post("/forecasts/demand", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["product_id"] == "FOODS_1_018"
    assert data[1]["product_id"] == "FOODS_1_019"



def test_forecast_rejects_unknown_product_instead_of_using_fallback():
    response = client.get(
        "/products/UNKNOWN_PRODUCT/forecast?start_date=2026-11-07&horizon_days=7"
    )
    assert response.status_code == 404


def test_forecast_rejects_non_selected_model():
    response = client.post(
        "/forecasts/demand",
        json={
            "product_ids": ["FOODS_1_018"],
            "start_date": "2026-11-07",
            "horizon_days": 7,
            "model": "naive",
        },
    )
    assert response.status_code == 422


def test_single_product_forecast_requires_start_date():
    response = client.get("/products/FOODS_1_018/forecast?horizon_days=7")
    assert response.status_code == 422


def test_single_product_forecast_rejects_other_models():
    response = client.get(
        "/products/FOODS_1_018/forecast?start_date=2026-11-07&horizon_days=7&model=naive"
    )
    assert response.status_code == 422
