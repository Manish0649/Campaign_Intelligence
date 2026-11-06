
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from tests.auth_helpers import auth_headers

from backend.app.db.repositories.inventory_repo import InventoryRepository

from backend.app.security.sanitizer import (
    mask_secret,
    sanitize_connection_string,
    sanitize_log_message,
    verify_text_clean_of_secrets,
)

from backend.app.decision.optimizer_adapter import DecisionAdapter

from backend.app.decision.models import (
    DecisionInput,
    DecisionOutput,
    CandidateOption,
)


client = TestClient(app, headers=auth_headers())


# --------------------------------------------------
# Test supplier evidence
# --------------------------------------------------

@pytest.fixture(autouse=True)
def provide_supplier_evidence(monkeypatch):
    """
    Supply deterministic, valid supplier data for API tests.

    This prevents test outcomes from depending on supplier
    records in the external NeonDB database.
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
# 1. Approval spending authority tests
# --------------------------------------------------

def test_unrecognized_role_approval_forbidden():
    """
    Unrecognized approver role must be rejected with HTTP 403.
    """

    create_resp = client.post(
        "/campaigns/proposals",
        json={
            "campaign_id": "CAMP-001",
        },
    )

    assert create_resp.status_code == 200, create_resp.text

    prop_id = create_resp.json()["proposal_id"]

    resp = client.post(
        f"/campaigns/proposals/{prop_id}/approval",
        json={
            "approver_id": "HACKER_1",
            "approver_role": "UNAUTHORIZED_INTERN",
            "action": "approve",
        },
        headers=auth_headers("UNAUTHORIZED_INTERN", "HACKER_1"),
    )

    assert resp.status_code == 403

    assert (
        "Unrecognized approver role"
        in resp.json()["detail"]
    )


def test_spending_limit_exceeded_forbidden():
    """
    Approver role with spending limit below campaign budget
    must be rejected with HTTP 403.

    CAMP-002 budget = $8,500
    MGR-MKT spending limit = $7,500
    """

    create_resp = client.post(
        "/campaigns/proposals",
        json={
            "campaign_id": "CAMP-002",
        },
    )

    assert create_resp.status_code == 200, create_resp.text

    prop_id = create_resp.json()["proposal_id"]

    resp = client.post(
        f"/campaigns/proposals/{prop_id}/approval",
        json={
            "approver_id": "MARKETING_COORDINATOR",
            "approver_role": "MGR-MKT",
            "action": "approve",
        },
        headers=auth_headers("MGR-MKT", "MARKETING_COORDINATOR"),
    )

    assert resp.status_code == 403

    assert (
        "Spending limit exceeded"
        in resp.json()["detail"]
    )


# --------------------------------------------------
# 2. Campaign activation governance tests
# --------------------------------------------------

def test_unapproved_proposal_activation_rejected():
    """
    Proposals with status pending_review cannot be activated.
    """

    create_resp = client.post(
        "/campaigns/proposals",
        json={
            "campaign_id": "CAMP-001",
        },
    )

    assert create_resp.status_code == 200, create_resp.text

    prop_id = create_resp.json()["proposal_id"]

    resp = client.post(
        f"/campaigns/proposals/{prop_id}/activation",
        json={
            "activator_id": "OPS_BOT",
            "channel": "meta_ads",
        },
        headers=auth_headers("OPS-MANAGER", "OPS_BOT"),
    )

    assert resp.status_code == 403

    assert (
        "Unauthorized activation"
        in resp.json()["detail"]
    )


def test_authorized_activation_and_duplicate_prevention():
    """
    Authorized flow:

    1. Human approves proposal within spending authority.
    2. Activation succeeds.
    3. Duplicate activation is rejected with HTTP 409.
    """

    # Create proposal.
    create_resp = client.post(
        "/campaigns/proposals",
        json={
            "campaign_id": "CAMP-001",
        },
    )

    assert create_resp.status_code == 200, create_resp.text

    prop_id = create_resp.json()["proposal_id"]

    # Approve using DIR-MKT.
    appr_resp = client.post(
        f"/campaigns/proposals/{prop_id}/approval",
        json={
            "approver_id": "DIR_JANE",
            "approver_role": "DIR-MKT",
            "action": "approve",
        },
        headers=auth_headers("DIR-MKT", "DIR_JANE"),
    )

    assert appr_resp.status_code == 200, appr_resp.text

    assert (
        appr_resp.json()["approval_status"]
        == "approved"
    )

    audit_after_approval = client.get(
        f"/campaigns/proposals/{prop_id}/audit",
        headers=auth_headers("DIR-MKT", "DIR_JANE"),
    )
    assert audit_after_approval.status_code == 200
    assert [event["event_type"] for event in audit_after_approval.json()["events"]] == [
        "proposal_created", "proposal_approved"
    ]

    # Activate approved proposal.
    act_resp = client.post(
        f"/campaigns/proposals/{prop_id}/activation",
        json={
            "activator_id": "OPS_MANAGER",
            "channel": "retail_pos",
        },
        headers=auth_headers("OPS-MANAGER", "OPS_MANAGER"),
    )

    assert act_resp.status_code == 200, act_resp.text

    assert act_resp.json()["status"] == "activated"

    # A duplicate activation must fail.
    dup_resp = client.post(
        f"/campaigns/proposals/{prop_id}/activation",
        json={
            "activator_id": "OPS_MANAGER",
            "channel": "retail_pos",
        },
        headers=auth_headers("OPS-MANAGER", "OPS_MANAGER"),
    )

    assert dup_resp.status_code == 409

    assert (
        "Duplicate activation request"
        in dup_resp.json()["detail"]
    )

    audit_after_activation = client.get(
        f"/campaigns/proposals/{prop_id}/audit",
        headers=auth_headers("OPS-MANAGER", "OPS_MANAGER"),
    )
    assert [event["event_type"] for event in audit_after_activation.json()["events"]] == [
        "proposal_created", "proposal_approved", "proposal_activated"
    ]



def test_proposal_creator_cannot_approve_own_proposal():
    creator_headers = auth_headers("DIR-MKT", "SAME_PERSON")
    created = client.post(
        "/campaigns/proposals",
        json={"campaign_id": "CAMP-001"},
        headers=creator_headers,
    )
    assert created.status_code == 200, created.text
    proposal_id = created.json()["proposal_id"]
    response = client.post(
        f"/campaigns/proposals/{proposal_id}/approval",
        json={"action": "approve"},
        headers=creator_headers,
    )
    assert response.status_code == 403
    assert "cannot approve their own" in response.json()["detail"]


def test_approval_requires_authentication():
    response = client.post(
        "/campaigns/proposals/PROP-NOT-IMPORTANT/approval",
        json={"action": "approve"},
        headers={"Authorization": ""},
    )
    assert response.status_code == 401


def test_request_body_cannot_forge_approver_role():
    created = client.post("/campaigns/proposals", json={"campaign_id": "CAMP-001"})
    assert created.status_code == 200, created.text
    proposal_id = created.json()["proposal_id"]
    response = client.post(
        f"/campaigns/proposals/{proposal_id}/approval",
        json={"approver_role": "DIR-MKT", "action": "approve"},
        headers=auth_headers("MGR-MKT", "MKT_USER"),
    )
    assert response.status_code == 403
    assert "derived from the authenticated identity" in response.json()["detail"]

# --------------------------------------------------
# 3. Secret management and log sanitization tests
# --------------------------------------------------

def test_secret_masking():
    """
    Verify that mask_secret masks tokens while preserving
    minimal debugging information.
    """

    fake_key = "AIzaSyD_EXAMPLE_SECRET_KEY_123456789"

    masked = mask_secret(fake_key)

    assert "AIza" in masked

    assert "89" in masked

    assert "EXAMPLE_SECRET" not in masked


def test_sanitize_connection_string():
    """
    Verify that database URI passwords are redacted.
    """

    raw_uri = (
        "postgresql://neon_user:SuperSecretPassword123"
        "@ep-cool-cloud.us-east-2.aws.neon.tech/neondb"
    )

    sanitized = sanitize_connection_string(raw_uri)

    assert "SuperSecretPassword123" not in sanitized

    assert (
        "postgresql://neon_user:***@ep-cool-cloud"
        in sanitized
    )


def test_sanitize_log_message():
    """
    Verify that API keys, bearer tokens and passwords
    are masked in log messages.
    """

    raw_log = (
        "Calling Gemini with key "
        "AIzaSyA1234567890abcdefghijklmnopqrstuv and "
        "Bearer "
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig and "
        "password='MySecretDbPass123!'"
    )

    sanitized = sanitize_log_message(raw_log)

    clean, leaks = verify_text_clean_of_secrets(
        sanitized,
        forbidden_values=[
            "MySecretDbPass123!",
            "AIzaSyA1234567890abcdefghijklmnopqrstuv",
        ],
    )

    assert clean is True, f"Leaks found: {leaks}"

    assert "AIzaSy***[MASKED_API_KEY]" in sanitized

    assert "***[MASKED_TOKEN]" in sanitized


# --------------------------------------------------
# 4. Decision layer safety guardrail tests
# --------------------------------------------------

def test_decision_adapter_rejects_unknown_campaign_id():
    """
    A rogue decision engine selecting an unknown campaign ID
    must be caught and rejected through fallback.
    """

    class RogueAdapter(DecisionAdapter):

        def __init__(self):
            super().__init__(
                name="rogue_test_adapter"
            )

        def _optimize_and_rank(
            self,
            feasible_candidates,
            decision_input,
        ):

            return DecisionOutput(
                forecast_version="m5-v1",
                candidate_campaign_ids=[
                    candidate.campaign_id
                    for candidate in feasible_candidates
                ],
                feasible_candidate_ids=[
                    candidate.campaign_id
                    for candidate in feasible_candidates
                ],
                selected_campaign_id="UNKNOWN_ROGUE_CAMPAIGN_999",
                ranked_candidates=[],
                objective_values={},
                constraint_validation_status="passed",
                decision_rationale="Malicious pick",
                framework_used=self.name,
                fallback_triggered=False,
                execution_latency_ms=0.0,
            )

    candidate = CandidateOption(
        campaign_id="CAMP-SAFE",
        campaign_name="Safe Promo",
        campaign_type="discount",
        target_product_ids=["P1"],
        target_segments="all",
        campaign_budget=5000.0,
        discount_rate=0.10,
        total_projected_cost=1000.0,
        projected_units=50.0,
        gross_revenue=5000.0,
        expected_contribution=2500.0,
        projected_supply=100,
        net_usable_stock=50,
        stock_coverage_ratio=1.5,
        stockout_risk_score=0.10,
        feasibility_status="feasible_for_review",
        is_feasible=True,
    )

    adapter = RogueAdapter()

    output = adapter.evaluate(
        DecisionInput(
            candidates=[candidate]
        )
    )

    assert output.fallback_triggered is True

    assert output.selected_campaign_id == "CAMP-SAFE"

    assert "Fallback Alert" in output.decision_rationale
