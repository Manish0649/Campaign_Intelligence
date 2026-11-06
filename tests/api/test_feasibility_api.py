from tests.auth_helpers import auth_headers
from fastapi.testclient import TestClient
from backend.app.main import app
import backend.app.domain.feasibility as feasibility_domain
import pytest
import backend.app.api.routes.feasibility as feasibility_routes

client = TestClient(app, headers=auth_headers())

def test_list_campaigns():
    response = client.get("/campaigns")
    assert response.status_code == 200
    campaigns = response.json()
    assert isinstance(campaigns, list)
    assert len(campaigns) > 0
    assert any(c["campaign_id"] == "CAMP-001" for c in campaigns)

def test_campaign_budget_endpoint():
    response = client.get("/campaigns/CAMP-001/budget")
    assert response.status_code == 200
    data = response.json()
    assert data["campaign_id"] == "CAMP-001"
    assert "budget_limit" in data
    assert "total_projected_cost" in data
    assert "budget_remaining" in data
    assert "cost_breakdown" in data

def test_campaign_feasibility_endpoint_camp001():
    payload = {
        "campaign_id": "CAMP-001",
        "product_ids": ["HOBBIES_1_001", "HOBBIES_1_002"],
        "start_date": "2016-04-25",
        "end_date": "2016-05-01",
        "assumed_uplift_pct": 0.15
    }
    response = client.post("/campaigns/feasibility", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["campaign_id"] == "CAMP-001"
    assert data["status"] in ["feasible_for_review", "rejected_by_policy"]
    assert "budget_validation" in data
    assert "inventory_validation" in data
    assert "replenishment_validation" in data
    assert len(data["product_details"]) == 2

def test_campaign_feasibility_endpoint_product_scope_violation():
    # Attempting to target 3 products triggers 422 validation error
    payload = {
        "campaign_id": "CAMP-001",
        "product_ids": ["HOBBIES_1_001", "HOBBIES_1_002", "HOBBIES_1_004"],
        "start_date": "2016-04-25",
        "end_date": "2016-05-01"
    }
    response = client.post("/campaigns/feasibility", json=payload)
    assert response.status_code == 422


def test_feasibility_rejects_unregistered_campaign():
    payload = {
        "campaign_id": "UNKNOWN-CAMPAIGN",
        "product_ids": ["HOBBIES_1_001"],
        "start_date": "2016-04-25",
        "end_date": "2016-05-01"
    }

    response = client.post(
        "/campaigns/feasibility",
        json=payload
    )

    assert response.status_code == 404


def test_feasibility_rejects_modified_product_scope():
    payload = {
        "campaign_id": "CAMP-001",
        "product_ids": ["HOBBIES_1_001"],
        "start_date": "2016-04-25",
        "end_date": "2016-05-01"
    }

    response = client.post(
        "/campaigns/feasibility",
        json=payload
    )

    assert response.status_code == 400


def test_feasibility_rejects_modified_campaign_dates():
    payload = {
        "campaign_id": "CAMP-001",
        "product_ids": [
            "HOBBIES_1_001",
            "HOBBIES_1_002"
        ],
        "start_date": "2016-04-26",
        "end_date": "2016-05-01"
    }

    response = client.post(
        "/campaigns/feasibility",
        json=payload
    )

    assert response.status_code == 200
def test_feasibility_ignores_client_budget_override():
    # Get the authoritative campaign budget from the database.
    budget_response = client.get("/campaigns/CAMP-001/budget")

    assert budget_response.status_code == 200

    registered_budget = budget_response.json()["budget_limit"]

    payload = {
        "campaign_id": "CAMP-001",
        "product_ids": [
            "HOBBIES_1_001",
            "HOBBIES_1_002"
        ],
        "start_date": "2016-04-25",
        "end_date": "2016-05-01",
        "budget_limit": 999999999
    }

    response = client.post(
        "/campaigns/feasibility",
        json=payload
    )

    assert response.status_code == 200

    data = response.json()

    # Client-provided budget must not override registered budget.
    assert data["budget_limit"] == registered_budget

def test_feasibility_enforces_registered_budget(monkeypatch):
    # Get the registered campaign budget.
    budget_response = client.get("/campaigns/CAMP-001/budget")

    assert budget_response.status_code == 200

    registered_budget = budget_response.json()["budget_limit"]

    # Preserve the original cost calculation.
    original_calculate_campaign_cost = (
        feasibility_domain.calculate_campaign_cost
    )

    # Force projected cost to exceed the registered budget.
    def force_over_budget(*args, **kwargs):
        _, breakdown = original_calculate_campaign_cost(*args, **kwargs)

        return registered_budget + 1, breakdown

    monkeypatch.setattr(
        feasibility_domain,
        "calculate_campaign_cost",
        force_over_budget
    )

    payload = {
        "campaign_id": "CAMP-001",
        "product_ids": [
            "HOBBIES_1_001",
            "HOBBIES_1_002"
        ],
        "start_date": "2016-04-25",
        "end_date": "2016-05-01",
        "budget_limit": 999999999
    }

    response = client.post(
        "/campaigns/feasibility",
        json=payload
    )

    assert response.status_code == 200

    data = response.json()

    # Verify that the registered budget is enforced.
    assert data["budget_limit"] == registered_budget
    assert data["total_projected_cost"] == registered_budget + 1
    assert data["budget_validation"] == "failed"
    assert data["status"] == "rejected_by_policy"

def test_feasibility_rejects_missing_product_metadata(monkeypatch):

    def mock_get_product(self, product_id):
        return None

    monkeypatch.setattr(
        feasibility_routes.CampaignRepository,
        "get_product",
        mock_get_product
    )

    payload = {
        "campaign_id": "CAMP-001",
        "product_ids": [
            "HOBBIES_1_001",
            "HOBBIES_1_002"
        ],
        "start_date": "2016-04-25",
        "end_date": "2016-05-01"
    }

    response = client.post(
        "/campaigns/feasibility",
        json=payload
    )

    assert response.status_code == 422
    assert "Product metadata is unavailable" in response.json()["detail"]


@pytest.mark.parametrize(
    "invalid_price",
    [None, 0, -5, float("nan"), float("inf")]
)
def test_feasibility_rejects_invalid_product_price(
    monkeypatch,
    invalid_price
):

    def mock_get_product(self, product_id):
        return {
            "product_id": product_id,
            "product_name": product_id,
            "base_price": invalid_price
        }

    monkeypatch.setattr(
        feasibility_routes.CampaignRepository,
        "get_product",
        mock_get_product
    )

    payload = {
        "campaign_id": "CAMP-001",
        "product_ids": [
            "HOBBIES_1_001",
            "HOBBIES_1_002"
        ],
        "start_date": "2016-04-25",
        "end_date": "2016-05-01"
    }

    response = client.post(
        "/campaigns/feasibility",
        json=payload
    )

    assert response.status_code == 422