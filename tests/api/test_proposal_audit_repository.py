from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.session import Base
from backend.app.db.models import CampaignModel
from backend.app.db.repositories.proposal_repo import ProposalRepository


def test_proposal_lifecycle_is_persisted_as_atomic_audit_events():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    try:
        db.add(
            CampaignModel(
                campaign_id="AUDIT-CAMP",
                campaign_name="Audit test campaign",
                campaign_type="discount",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 7),
                target_product_ids="SKU-1",
                target_product_names="Test SKU",
                target_segments="test",
                campaign_budget=1000,
                discount_rate=0.1,
                status="candidate",
                scenario_label="test",
            )
        )
        db.commit()

        repository = ProposalRepository(db)
        repository.save_proposal(
            proposal_id="AUDIT-PROP",
            campaign_id="AUDIT-CAMP",
            forecast_version="test-v1",
            decision_status="ranked_feasible",
            selected_option_id="OPT-1",
            budget_validation_status="passed",
            inventory_validation_status="passed",
            created_by="CREATOR",
            created_by_role="SYS-ADMIN",
        )
        approved = repository.update_approval(
            proposal_id="AUDIT-PROP",
            approval_status="approved",
            approver_id="APPROVER",
            approver_role="DIR-MKT",
            comments="Reviewed and approved",
        )
        activated = repository.update_activation(
            proposal_id="AUDIT-PROP",
            activator_id="OPERATOR",
            activator_role="OPS-MANAGER",
            channel="retail_pos",
        )

        assert approved.approval_status == "approved"
        assert activated.activated_at is not None
        assert db.query(CampaignModel).filter_by(campaign_id="AUDIT-CAMP").one().status == "active"
        events = repository.get_audit_events("AUDIT-PROP")
        assert [event["event_type"] for event in events] == [
            "proposal_created",
            "proposal_approved",
            "proposal_activated",
        ]
        assert events[0]["actor_id"] == "CREATOR"
        assert events[1]["actor_role"] == "DIR-MKT"
        assert events[1]["details"]["comments"] == "Reviewed and approved"
        assert events[2]["details"]["channel"] == "retail_pos"

        with pytest.raises(ValueError, match="Duplicate activation"):
            repository.update_activation(
                proposal_id="AUDIT-PROP",
                activator_id="OPERATOR-2",
                activator_role="OPS-MANAGER",
                channel="retail_pos",
            )
        assert len(repository.get_audit_events("AUDIT-PROP")) == 3
    finally:
        db.close()
        engine.dispose()
