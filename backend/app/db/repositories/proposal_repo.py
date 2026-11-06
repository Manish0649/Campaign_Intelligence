
from datetime import datetime, timezone
import uuid

from sqlalchemy.orm import Session

from backend.app.db.models import CampaignProposalModel, ProposalAuditEventModel, CampaignModel
from backend.app.api.schemas.proposal import ProposalResponse


def utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ProposalRepository:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _to_response(model: CampaignProposalModel) -> ProposalResponse:
        return ProposalResponse(
            proposal_id=model.proposal_id,
            campaign_id=model.campaign_id,
            forecast_version=model.forecast_version,
            decision_status=model.decision_status,
            selected_option_id=model.selected_option_id,
            budget_validation_status=model.budget_validation_status,
            inventory_validation_status=model.inventory_validation_status,
            approval_status=model.approval_status,
            approver_id=model.approver_id,
            created_at=model.created_at,
            approved_at=model.approved_at,
            activated_at=model.activated_at
        )

    def save_proposal(
        self,
        proposal_id: str,
        campaign_id: str,
        forecast_version: str,
        decision_status: str,
        selected_option_id: str,
        budget_validation_status: str,
        inventory_validation_status: str,
        approval_status: str = "pending_review",
        approver_id: str = "PENDING_ASSIGNMENT",
        created_by: str = "SYSTEM_API",
        created_by_role: str = "SYSTEM",
    ) -> ProposalResponse:

        model = CampaignProposalModel(
            proposal_id=proposal_id,
            campaign_id=campaign_id,
            forecast_version=forecast_version,
            decision_status=decision_status,
            selected_option_id=selected_option_id,
            budget_validation_status=budget_validation_status,
            inventory_validation_status=inventory_validation_status,
            approval_status=approval_status,
            approver_id=approver_id,
            created_at=utcnow_naive()
        )

        try:
            self.db.add(model)
            self._add_audit_event(
                proposal_id=proposal_id,
                event_type="proposal_created",
                actor_id=created_by,
                actor_role=created_by_role,
                details={"approval_status": approval_status, "decision_status": decision_status},
            )
            self.db.commit()
            self.db.refresh(model)

        except Exception as exc:
            self.db.rollback()
            raise RuntimeError(
                f"Failed to save proposal '{proposal_id}' to the database."
            ) from exc

        return self._to_response(model)

    def _add_audit_event(
        self,
        proposal_id: str,
        event_type: str,
        actor_id: str,
        actor_role: str,
        details: dict | None = None,
    ) -> None:
        self.db.add(
            ProposalAuditEventModel(
                event_id=str(uuid.uuid4()),
                proposal_id=proposal_id,
                event_type=event_type,
                actor_id=actor_id,
                actor_role=actor_role,
                details=details or {},
                created_at=utcnow_naive(),
            )
        )

    def get_audit_events(self, proposal_id: str) -> list[dict]:
        events = (
            self.db.query(ProposalAuditEventModel)
            .filter(ProposalAuditEventModel.proposal_id == proposal_id)
            .order_by(ProposalAuditEventModel.created_at.asc())
            .all()
        )
        return [
            {
                "event_id": event.event_id,
                "proposal_id": event.proposal_id,
                "event_type": event.event_type,
                "actor_id": event.actor_id,
                "actor_role": event.actor_role,
                "details": event.details or {},
                "created_at": event.created_at,
            }
            for event in events
        ]

    def list_proposals(self) -> list[dict]:
        """Return proposal summaries with the creator identity from audit history."""
        try:
            models = (
                self.db.query(CampaignProposalModel)
                .order_by(CampaignProposalModel.created_at.desc())
                .all()
            )
            proposal_ids = [item.proposal_id for item in models]
            creator_events = []
            if proposal_ids:
                creator_events = (
                    self.db.query(ProposalAuditEventModel)
                    .filter(
                        ProposalAuditEventModel.proposal_id.in_(proposal_ids),
                        ProposalAuditEventModel.event_type == "proposal_created",
                    )
                    .all()
                )
            creators = {event.proposal_id: event.actor_id for event in creator_events}
            results = []
            for model in models:
                item = self._to_response(model).model_dump(mode="json")
                item["created_by"] = creators.get(model.proposal_id)
                results.append(item)
            return results
        except Exception as exc:
            raise RuntimeError("Failed to list campaign proposals.") from exc

    def get_proposal(self, proposal_id: str):
        try:
            model = (
                self.db.query(CampaignProposalModel)
                .filter(
                    CampaignProposalModel.proposal_id == proposal_id
                )
                .first()
            )

        except Exception as exc:
            raise RuntimeError(
                f"Failed to retrieve proposal '{proposal_id}' from the database."
            ) from exc

        if model is None:
            return None

        return self._to_response(model)

    def update_approval(
        self,
        proposal_id: str,
        approval_status: str,
        approver_id: str,
        approver_role: str = "UNKNOWN",
        comments: str | None = None,
    ):
        """Atomically transition a pending proposal to a terminal state."""
        if approval_status not in {"approved", "rejected"}:
            raise ValueError("Invalid approval status.")

        try:
            now = utcnow_naive()
            result = (
                self.db.query(CampaignProposalModel)
                .filter(
                    CampaignProposalModel.proposal_id == proposal_id,
                    CampaignProposalModel.approval_status == "pending_review",
                )
                .update(
                    {
                        CampaignProposalModel.approval_status: approval_status,
                        CampaignProposalModel.approver_id: approver_id,
                        CampaignProposalModel.approved_at: now if approval_status == "approved" else None,
                    },
                    synchronize_session="fetch",
                )
            )
            if result == 0:
                existing = self.db.query(CampaignProposalModel).filter(
                    CampaignProposalModel.proposal_id == proposal_id
                ).first()
                if existing is None:
                    return None
                raise ValueError(
                    f"Cannot update approval because proposal '{proposal_id}' "
                    f"is already {existing.approval_status}."
                )
            self._add_audit_event(
                proposal_id=proposal_id,
                event_type=f"proposal_{approval_status}",
                actor_id=approver_id,
                actor_role=approver_role,
                details={"approval_status": approval_status, "comments": comments},
            )
            self.db.commit()
            model = self.db.query(CampaignProposalModel).filter(
                CampaignProposalModel.proposal_id == proposal_id
            ).first()
            return self._to_response(model)
        except ValueError:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            raise RuntimeError(
                f"Failed to update approval for proposal '{proposal_id}'."
            ) from exc

    def update_activation(
        self,
        proposal_id: str,
        activator_id: str,
        activator_role: str = "UNKNOWN",
        channel: str = "marketing_ops",
    ):
        """Atomically activate an approved, not-yet-activated proposal."""
        try:
            now = utcnow_naive()
            result = (
                self.db.query(CampaignProposalModel)
                .filter(
                    CampaignProposalModel.proposal_id == proposal_id,
                    CampaignProposalModel.approval_status == "approved",
                    CampaignProposalModel.activated_at.is_(None),
                )
                .update(
                    {CampaignProposalModel.activated_at: now},
                    synchronize_session="fetch",
                )
            )
            if result == 0:
                existing = self.db.query(CampaignProposalModel).filter(
                    CampaignProposalModel.proposal_id == proposal_id
                ).first()
                if existing is None:
                    return None
                if existing.activated_at is not None:
                    raise ValueError("Duplicate activation request: proposal has already been activated.")
                raise ValueError("Only approved proposals can be activated.")
            proposal_model = self.db.query(CampaignProposalModel).filter(
                CampaignProposalModel.proposal_id == proposal_id
            ).first()
            if proposal_model is None:
                raise ValueError(f"Proposal '{proposal_id}' disappeared during activation.")
            campaign_update = (
                self.db.query(CampaignModel)
                .filter(CampaignModel.campaign_id == proposal_model.campaign_id)
                .update({CampaignModel.status: "active"}, synchronize_session="fetch")
            )
            if campaign_update == 0:
                raise ValueError("Campaign record could not be transitioned to active.")

            self._add_audit_event(
                proposal_id=proposal_id,
                event_type="proposal_activated",
                actor_id=activator_id,
                actor_role=activator_role,
                details={"channel": channel},
            )
            self.db.commit()
            model = self.db.query(CampaignProposalModel).filter(
                CampaignProposalModel.proposal_id == proposal_id
            ).first()
            return self._to_response(model)
        except ValueError:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            raise RuntimeError(
                f"Failed to activate proposal '{proposal_id}'."
            ) from exc

