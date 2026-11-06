from fastapi.testclient import TestClient
from backend.app.main import app
import pytest
from tests.auth_helpers import auth_headers

client = TestClient(app, headers=auth_headers())

def test_create_and_retrieve_proposal():
    # 1. Create Proposal for CAMP-001
    create_payload = {
        "campaign_id": "CAMP-001",
        "forecast_version": "m5-dynamic-linear-v2",
        "selected_option_id": "OPT-1-STANDARD"
    }
    create_res = client.post("/campaigns/proposals", json=create_payload)
    assert create_res.status_code == 200
    prop = create_res.json()
    assert "proposal_id" in prop
    proposal_id = prop["proposal_id"]
    assert prop["campaign_id"] == "CAMP-001"
    assert prop["approval_status"] in ["pending_review", "approved", "rejected"]

    # 2. Retrieve Proposal
    get_res = client.get(f"/campaigns/proposals/{proposal_id}")
    assert get_res.status_code == 200
    retrieved = get_res.json()
    assert retrieved["proposal_id"] == proposal_id

    # Creation is recorded as a persistent audit event.
    audit_res = client.get(f"/campaigns/proposals/{proposal_id}/audit")
    assert audit_res.status_code == 200
    events = audit_res.json()["events"]
    assert len(events) == 1
    assert events[0]["event_type"] == "proposal_created"

def test_proposal_approval_role_spending_limit_exceeded():
    # Create proposal for CAMP-002 ($8,500 budget)
    create_res = client.post("/campaigns/proposals", json={"campaign_id": "CAMP-002"})
    assert create_res.status_code == 200
    proposal_id = create_res.json()["proposal_id"]

    # MGR-MKT has spending limit $7,500 < $8,500 budget -> Should return 403 Forbidden
    approval_payload = {
        "approver_id": "MKT_USER_01",
        "approver_role": "MGR-MKT",
        "action": "approve"
    }
    appr_res = client.post(f"/campaigns/proposals/{proposal_id}/approval", json=approval_payload, headers=auth_headers("MGR-MKT", "MKT_USER_01"))
    assert appr_res.status_code == 403
    assert "Spending limit exceeded" in appr_res.json()["detail"]

def test_proposal_approval_with_authorized_role():
    # Create proposal for CAMP-001 ($5,000 budget)
    create_res = client.post("/campaigns/proposals", json={"campaign_id": "CAMP-001"})
    assert create_res.status_code == 200
    prop = create_res.json()

    print("\nPROPOSAL CREATION RESPONSE:")
    print(prop)

    proposal_id = prop["proposal_id"]

    # MGR-STORE has limit $10,000 >= $5,000 -> Should approve successfully
    approval_payload = {
        "approver_id": "STORE_MGR_CA1",
        "approver_role": "MGR-STORE",
        "action": "approve"
    }
    appr_res = client.post(f"/campaigns/proposals/{proposal_id}/approval", json=approval_payload, headers=auth_headers("MGR-STORE", "STORE_MGR_CA1"))
    assert appr_res.status_code == 200
    data = appr_res.json()
    assert data["approval_status"] == "approved"
    assert data["revalidation_status"] == "passed"

    # Duplicate approval request returns existing status without error
    dup_res = client.post(f"/campaigns/proposals/{proposal_id}/approval", json=approval_payload, headers=auth_headers("MGR-STORE", "STORE_MGR_CA1"))
    assert dup_res.status_code == 200
    assert dup_res.json()["revalidation_status"] == "already_processed"

