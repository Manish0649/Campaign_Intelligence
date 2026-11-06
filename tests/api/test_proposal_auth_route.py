from datetime import date, datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.routes import proposals
from backend.app.db.session import Base, get_db
from backend.app.db.models import (
    ProductModel,
    CampaignModel,
    CampaignCostAssumptionModel,
    InventorySnapshotModel,
    SupplierReplenishmentModel,
)
from backend.app.security.auth import create_access_token


def _headers(role: str, subject: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject, role)}"}


def test_proposal_approval_and_activation_use_signed_identity_and_audit_events():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    api = FastAPI()
    api.include_router(proposals.router)
    api.dependency_overrides[get_db] = override_get_db
    client = TestClient(api)

    db = session_factory()
    try:
        products = ["HOBBIES_1_001", "HOBBIES_1_002"]
        for product_id in products:
            db.add(ProductModel(
                product_id=product_id,
                product_name=product_id,
                cat_id="HOBBIES_1",
                dept_id="HOBBIES_1",
                store_id="CA_1",
                base_price=10.0,
            ))
        db.flush()
        db.add(CampaignModel(
            campaign_id="AUTH-CAMP",
            campaign_name="Auth governance campaign",
            campaign_type="discount",
            start_date=date(2016, 4, 25),
            end_date=date(2016, 5, 1),
            target_product_ids=";".join(products),
            target_product_names="Test products",
            target_segments="test",
            campaign_budget=5000.0,
            discount_rate=0.10,
            status="candidate",
            scenario_label="auth-test",
        ))
        db.flush()
        db.add(CampaignCostAssumptionModel(
            campaign_id="AUTH-CAMP",
            fixed_campaign_cost=100,
            cost_per_contact=0.01,
            discount_cost_assumption="retailer_absorbed",
            logistics_cost_assumption=0.10,
            cost_accounting_method="test",
        ))
        for product_id in products:
            db.add(InventorySnapshotModel(
                product_id=product_id,
                product_name=product_id,
                store_id="CA_1",
                on_hand_stock=10000,
                reserved_stock=0,
                available_stock=10000,
                safety_stock=100,
                inventory_updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            ))
            db.add(SupplierReplenishmentModel(
                supplier_id=f"SUPP-{product_id}",
                product_id=product_id,
                product_name=product_id,
                lead_time_days=4,
                minimum_order_quantity=20,
                replenishment_capacity=5000,
                expected_replenishment_date=date(2016, 4, 26),
                supplier_status="active",
            ))
        db.commit()
    finally:
        db.close()

    try:
        created = client.post(
            "/campaigns/proposals",
            json={"campaign_id": "AUTH-CAMP"},
            headers=_headers("SYS-ADMIN", "campaign.creator"),
        )
        assert created.status_code == 200, created.text
        proposal_id = created.json()["proposal_id"]

        unauthenticated = client.get(
            f"/campaigns/proposals/{proposal_id}",
            headers={"Authorization": ""},
        )
        assert unauthenticated.status_code == 401

        self_approval = client.post(
            f"/campaigns/proposals/{proposal_id}/approval",
            json={"action": "approve"},
            headers=_headers("SYS-ADMIN", "campaign.creator"),
        )
        assert self_approval.status_code == 403

        forged = client.post(
            f"/campaigns/proposals/{proposal_id}/approval",
            json={"action": "approve", "approver_role": "SYS-ADMIN"},
            headers=_headers("MGR-MKT", "marketing.director"),
        )
        assert forged.status_code == 403

        approved = client.post(
            f"/campaigns/proposals/{proposal_id}/approval",
            json={"action": "approve", "comments": "Reviewed by director"},
            headers=_headers("DIR-MKT", "marketing.director"),
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["approver_id"] == "marketing.director"
        assert approved.json()["approver_role"] == "DIR-MKT"

        self_activation = client.post(
            f"/campaigns/proposals/{proposal_id}/activation",
            json={"channel": "retail_pos"},
            headers=_headers("OPS-MANAGER", "marketing.director"),
        )
        assert self_activation.status_code == 403

        activated = client.post(
            f"/campaigns/proposals/{proposal_id}/activation",
            json={"channel": "retail_pos"},
            headers=_headers("OPS-MANAGER", "operations.manager"),
        )
        assert activated.status_code == 200, activated.text
        db = session_factory()
        try:
            assert db.query(CampaignModel).filter_by(campaign_id="AUTH-CAMP").one().status == "active"
        finally:
            db.close()

        duplicate = client.post(
            f"/campaigns/proposals/{proposal_id}/activation",
            json={"channel": "retail_pos"},
            headers=_headers("OPS-MANAGER", "operations.manager"),
        )
        assert duplicate.status_code == 409

        audit = client.get(
            f"/campaigns/proposals/{proposal_id}/audit",
            headers=_headers("SYS-ADMIN", "auditor"),
        )
        assert audit.status_code == 200
        assert [event["event_type"] for event in audit.json()["events"]] == [
            "proposal_created", "proposal_approved", "proposal_activated"
        ]
    finally:
        client.close()
        engine.dispose()


def test_proposal_submitter_account_can_login(monkeypatch):
    """The dedicated proposal account receives a submitter-only JWT role."""
    from backend.app.api.routes.auth import LoginRequest, login
    from backend.app.config import settings

    monkeypatch.setattr(settings, "auth_users_json", "")
    monkeypatch.setattr(settings, "admin_email", "")
    monkeypatch.setattr(settings, "admin_password", "")
    monkeypatch.setattr(settings, "proposal_user_email", "submitter@campaign.local")
    monkeypatch.setattr(settings, "proposal_user_password", "a-strong-test-password-123")

    response = login(LoginRequest(
        email="submitter@campaign.local",
        password="a-strong-test-password-123",
    ))
    assert response.role == "PROPOSAL-SUBMITTER"
    assert response.access_token
