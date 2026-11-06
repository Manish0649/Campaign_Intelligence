from tests.auth_helpers import auth_headers

from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.repositories.inventory_repo import InventoryRepository

from backend.app.decision.models import (
    CandidateOption,
    DecisionInput,
)
from backend.app.decision.baseline_ranker import BaselineRanker
from backend.app.decision.laya_adapter import LayaAdapter


client = TestClient(app, headers=auth_headers())


# --------------------------------------------------
# Test supplier evidence
# --------------------------------------------------

@pytest.fixture(autouse=True)
def provide_supplier_evidence(monkeypatch):
    """
    Provide valid supplier evidence for test products.

    The SQLite test database may not contain supplier
    replenishment records. This fixture supplies deterministic
    test data without weakening production feasibility rules.
    """

    def mock_get_supplier_replenishment(self, product_id):
        return {
            "supplier_id": f"SUPP_{product_id}",
            "product_id": product_id,
            "product_name": f"Test Product {product_id}",
            "lead_time_days": 4,
            "minimum_order_quantity": 20,
            "replenishment_capacity": 200,
            "expected_replenishment_date": date(2016, 4, 26),
            "supplier_status": "active",
        }

    monkeypatch.setattr(
        InventoryRepository,
        "get_supplier_replenishment",
        mock_get_supplier_replenishment,
    )


# --------------------------------------------------
# Sample candidates
# --------------------------------------------------

@pytest.fixture
def sample_candidates():

    c1 = CandidateOption(
        campaign_id="CAMP-001",
        campaign_name="Creative Flash Sale",
        campaign_type="flash_sale",
        target_product_ids=["HOBBIES_1_001", "HOBBIES_1_002"],
        target_segments="craft_enthusiasts",
        campaign_budget=5000.0,
        discount_rate=0.15,
        total_projected_cost=1500.0,
        projected_units=25.0,
        gross_revenue=3500.0,
        expected_contribution=2000.0,
        projected_supply=40,
        net_usable_stock=20,
        stock_coverage_ratio=1.60,
        stockout_risk_score=0.15,
        feasibility_status="feasible_for_review",
        is_feasible=True,
    )

    c2 = CandidateOption(
        campaign_id="CAMP-002",
        campaign_name="Pantry Bulk Saver",
        campaign_type="weekly_special",
        target_product_ids=["FOODS_3_586", "FOODS_3_090"],
        target_segments="bulk_buyers",
        campaign_budget=8500.0,
        discount_rate=0.10,
        total_projected_cost=2200.0,
        projected_units=50.0,
        gross_revenue=6000.0,
        expected_contribution=3800.0,
        projected_supply=90,
        net_usable_stock=50,
        stock_coverage_ratio=1.80,
        stockout_risk_score=0.10,
        feasibility_status="feasible_for_review",
        is_feasible=True,
    )

    c3_infeasible = CandidateOption(
        campaign_id="CAMP-003",
        campaign_name="Clearance Blowout",
        campaign_type="clearance",
        target_product_ids=["HOBBIES_1_004"],
        target_segments="bargain_hunters",
        campaign_budget=3000.0,
        discount_rate=0.30,
        total_projected_cost=1200.0,
        projected_units=80.0,
        gross_revenue=7000.0,
        expected_contribution=5800.0,
        projected_supply=10,
        net_usable_stock=5,
        stock_coverage_ratio=0.12,
        stockout_risk_score=0.95,
        feasibility_status="rejected_by_policy",
        is_feasible=False,
    )

    return [c1, c2, c3_infeasible]


# --------------------------------------------------
# 1. Baseline ranker tests
# --------------------------------------------------

def test_baseline_ranker_filters_infeasible(sample_candidates):

    ranker = BaselineRanker()

    dec_input = DecisionInput(
        candidates=sample_candidates
    )

    output = ranker.rank(dec_input)

    assert output.constraint_validation_status == "passed"

    # Infeasible campaign must never be selected.
    assert "CAMP-003" not in output.feasible_candidate_ids

    assert output.selected_campaign_id == "CAMP-002"

    assert len(output.ranked_candidates) == 2

    assert output.ranked_candidates[0].campaign_id == "CAMP-002"
    assert output.ranked_candidates[1].campaign_id == "CAMP-001"


# --------------------------------------------------
# 2. Laya adapter tests
# --------------------------------------------------

def test_laya_adapter_evaluation(sample_candidates):

    adapter = LayaAdapter()

    dec_input = DecisionInput(
        candidates=sample_candidates,
        framework="laya",
    )

    output = adapter.evaluate(dec_input)

    assert output.framework_used == "laya_decision_adapter"

    assert output.selected_campaign_id in [
        "CAMP-001",
        "CAMP-002",
    ]

    assert "CAMP-003" not in output.feasible_candidate_ids

    assert output.fallback_triggered is False

    assert len(output.ranked_candidates) == 2

    assert "composite_score" in output.objective_values


# --------------------------------------------------
# 3. Hard constraint tests
# --------------------------------------------------

def test_hard_constraint_inviolability_cannot_be_bypassed():
    """
    Decision layer cannot make an infeasible campaign valid.
    """

    infeasible_only = [
        CandidateOption(
            campaign_id="CAMP-999",
            campaign_name="Illegal Campaign",
            campaign_type="flash",
            target_product_ids=["P1"],
            target_segments="bulk_buyers",
            campaign_budget=1000.0,
            discount_rate=0.20,
            total_projected_cost=1500.0,
            projected_units=100.0,
            gross_revenue=5000.0,
            expected_contribution=3500.0,
            projected_supply=50,
            net_usable_stock=20,
            stock_coverage_ratio=0.5,
            stockout_risk_score=0.9,
            feasibility_status="rejected_by_policy",
            is_feasible=False,
        )
    ]

    adapter = LayaAdapter()

    dec_input = DecisionInput(
        candidates=infeasible_only
    )

    output = adapter.evaluate(dec_input)

    assert output.selected_campaign_id is None

    assert output.approval_status == "rejected"

    assert (
        output.constraint_validation_status
        == "failed_no_feasible_candidates"
    )


# --------------------------------------------------
# 4. Decision rank API test
# --------------------------------------------------

def test_api_decision_rank_endpoint(sample_candidates):

    payload = {
        "candidates": [
            candidate.model_dump()
            for candidate in sample_candidates
        ],
        "framework": "laya",
        "weights": {
            "expected_contribution": 0.40,
            "inventory_suitability": 0.30,
            "stockout_exposure_reduction": 0.15,
            "cost_efficiency": 0.10,
            "segment_priority": 0.05,
        },
    }

    response = client.post(
        "/decision/rank",
        json=payload,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["selected_campaign_id"] in [
        "CAMP-001",
        "CAMP-002",
    ]

    assert len(data["ranked_candidates"]) == 2


# --------------------------------------------------
# 5. End-to-end orchestration API test
# --------------------------------------------------

def test_api_orchestration_endpoint():
    """
    End-to-end LangGraph planning test.

    The test database and supplier evidence are provided
    through the shared test fixtures.
    """

    payload = {
        "campaign_ids": [
            "CAMP-001",
            "CAMP-002",
            "CAMP-003",
        ],
        "decision_framework": "laya",
        "assumed_uplift_pct": 0.20,
    }

    response = client.post(
        "/decision/orchestrate",
        json=payload,
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["status"] == "success"

    assert data["current_step"] == "proposal_generated"

    assert data["selected_campaign"] in [
        "CAMP-001",
        "CAMP-002",
    ]

    assert data["generated_proposal"] is not None

    assert (
        data["generated_proposal"]["approval_status"]
        == "pending_review"
    )

    assert len(data["audit_log"]) >= 4
