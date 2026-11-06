
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.api.routes import proposals
from backend.app.api.schemas.proposal import (
    ApprovalRequest,
    ActivationRequest
)


def make_proposal(
    approval_status="pending_review",
    activated_at=None
):
    return SimpleNamespace(
        proposal_id="PROP-TEST-001",
        campaign_id="CAMP-001",
        approval_status=approval_status,
        approver_id="PENDING_ASSIGNMENT",
        approved_at=None,
        activated_at=activated_at
    )


def make_approval_request(action="approve"):
    return ApprovalRequest(
        approver_id="TEST-APPROVER",
        approver_role="MGR-MKT",
        action=action
    )


def make_activation_request():
    return ActivationRequest(
        activator_id="TEST-ACTIVATOR",
        channel="marketing_ops"
    )


@pytest.fixture
def mock_repositories():
    with (
        patch.object(proposals, "ProposalRepository") as prop_repo_cls,
        patch.object(proposals, "CampaignRepository") as camp_repo_cls,
        patch.object(proposals, "InventoryRepository") as inv_repo_cls
    ):
        prop_repo = prop_repo_cls.return_value
        camp_repo = camp_repo_cls.return_value
        inv_repo = inv_repo_cls.return_value

        yield prop_repo, camp_repo, inv_repo


def test_approve_pending_proposal(mock_repositories):
    prop_repo, camp_repo, inv_repo = mock_repositories

    proposal = make_proposal()
    prop_repo.get_proposal.return_value = proposal

    camp_repo.get_campaign.return_value = {
        "campaign_id": "CAMP-001",
        "campaign_budget": 5000.0,
        "target_product_ids": ["PROD-001"],
        "start_date": "2016-04-25",
        "end_date": "2016-05-01"
    }

    inv_repo.get_inventory_snapshot.return_value = {
        "on_hand_stock": 1000,
        "reserved_stock": 100,
        "safety_stock": 200
    }

    inv_repo.get_supplier_replenishment.return_value = {
        "supplier_id": "SUPP-001",
        "product_id": "PROD-001",
        "supplier_status": "active",
        "lead_time_days": 4,
        "minimum_order_quantity": 20,
        "replenishment_capacity": 200,
        "expected_replenishment_date": date(2016, 4, 26)
    }

    updated_proposal = make_proposal("approved")
    updated_proposal.approved_at = datetime.now(timezone.utc).replace(tzinfo=None)

    prop_repo.update_approval.return_value = updated_proposal

    response = proposals.approve_or_reject_proposal(
        proposal_id="PROP-TEST-001",
        request=make_approval_request("approve"),
        db=MagicMock(),
        current_user={"sub": "TEST-APPROVER", "role": "MGR-MKT"}
    )

    assert response.approval_status == "approved"
    assert response.revalidation_status == "passed"

    prop_repo.update_approval.assert_called_once_with(
        proposal_id="PROP-TEST-001",
        approval_status="approved",
        approver_id="TEST-APPROVER",
        approver_role="MGR-MKT",
        comments=None,
    )


def test_reject_pending_proposal(mock_repositories):
    prop_repo, camp_repo, inv_repo = mock_repositories

    proposal = make_proposal()
    prop_repo.get_proposal.return_value = proposal

    camp_repo.get_campaign.return_value = {
        "campaign_id": "CAMP-001",
        "campaign_budget": 5000.0,
        "target_product_ids": ["PROD-001"],
        "start_date": "2016-04-25",
        "end_date": "2016-05-01"
    }

    updated_proposal = make_proposal("rejected")
    prop_repo.update_approval.return_value = updated_proposal

    response = proposals.approve_or_reject_proposal(
        proposal_id="PROP-TEST-001",
        request=make_approval_request("reject"),
        db=MagicMock(),
        current_user={"sub": "TEST-APPROVER", "role": "MGR-MKT"}
    )

    assert response.approval_status == "rejected"
    assert response.revalidation_status == "not_applicable"

    inv_repo.get_inventory_snapshot.assert_not_called()
    inv_repo.get_supplier_replenishment.assert_not_called()


def test_rejected_proposal_cannot_be_activated(mock_repositories):
    prop_repo, _, _ = mock_repositories

    prop_repo.get_proposal.return_value = make_proposal("rejected")

    with pytest.raises(HTTPException) as exc:
        proposals.activate_campaign_proposal(
            proposal_id="PROP-TEST-001",
            request=make_activation_request(),
            db=MagicMock(),
            current_user={"sub": "TEST-ACTIVATOR", "role": "SYS-ADMIN"}
        )

    assert exc.value.status_code == 403
    prop_repo.update_activation.assert_not_called()


def test_approved_proposal_can_be_activated(mock_repositories):
    prop_repo, camp_repo, inv_repo = mock_repositories

    proposal = make_proposal("approved")
    prop_repo.get_proposal.return_value = proposal
    camp_repo.get_campaign.return_value = {
        "campaign_id": "CAMP-001",
        "start_date": date(2016, 4, 25),
        "end_date": date(2016, 5, 1),
        "target_product_ids": ["PROD-001"],
    }
    inv_repo.get_inventory_snapshot.return_value = {
        "on_hand_stock": 1000,
        "reserved_stock": 100,
        "safety_stock": 200,
    }
    inv_repo.get_supplier_replenishment.return_value = {
        "supplier_status": "active",
        "lead_time_days": 4,
        "minimum_order_quantity": 20,
        "replenishment_capacity": 200,
        "expected_replenishment_date": date(2016, 4, 26),
    }

    activated_proposal = make_proposal(
        approval_status="approved",
        activated_at=datetime.now(timezone.utc).replace(tzinfo=None)
    )

    prop_repo.update_activation.return_value = activated_proposal

    response = proposals.activate_campaign_proposal(
        proposal_id="PROP-TEST-001",
        request=make_activation_request(),
        db=MagicMock(),
        current_user={"sub": "TEST-ACTIVATOR", "role": "SYS-ADMIN"}
    )

    assert response.status == "activated"
    assert response.activated_at is not None

    prop_repo.update_activation.assert_called_once_with(
        proposal_id="PROP-TEST-001",
        activator_id="TEST-ACTIVATOR",
        activator_role="SYS-ADMIN",
        channel="marketing_ops",
    )


def test_already_activated_proposal_cannot_be_activated(mock_repositories):
    prop_repo, _, _ = mock_repositories

    proposal = make_proposal(
        approval_status="approved",
        activated_at=datetime.now(timezone.utc).replace(tzinfo=None)
    )

    prop_repo.get_proposal.return_value = proposal

    with pytest.raises(HTTPException) as exc:
        proposals.activate_campaign_proposal(
            proposal_id="PROP-TEST-001",
            request=make_activation_request(),
            db=MagicMock(),
            current_user={"sub": "TEST-ACTIVATOR", "role": "SYS-ADMIN"}
        )

    assert exc.value.status_code == 409
    prop_repo.update_activation.assert_not_called()


def test_pending_proposal_cannot_be_activated(mock_repositories):
    prop_repo, _, _ = mock_repositories

    prop_repo.get_proposal.return_value = make_proposal("pending_review")

    with pytest.raises(HTTPException) as exc:
        proposals.activate_campaign_proposal(
            proposal_id="PROP-TEST-001",
            request=make_activation_request(),
            db=MagicMock(),
            current_user={"sub": "TEST-ACTIVATOR", "role": "SYS-ADMIN"}
        )

    assert exc.value.status_code == 403
    prop_repo.update_activation.assert_not_called()


def test_invalid_approval_action_is_rejected():
    with pytest.raises(ValidationError):
        ApprovalRequest(
            approver_id="TEST-APPROVER",
            approver_role="MGR-MKT",
            action="launch"
        )
