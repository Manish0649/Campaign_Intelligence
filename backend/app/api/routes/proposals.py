
import uuid
import math

from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from backend.app.db.session import get_db

from backend.app.api.schemas.proposal import (
    ProposalCreate,
    ProposalResponse,
    ApprovalRequest,
    ApprovalResponse,
    FeasibilityRequest,
    ActivationRequest,
    ActivationResponse,
)

from backend.app.db.repositories.proposal_repo import ProposalRepository
from backend.app.db.repositories.campaign_repo import CampaignRepository
from backend.app.db.repositories.inventory_repo import InventoryRepository

from backend.app.db.repositories.forecast_repo import (
    FORECAST_MODEL,
    ForecastDataError,
    ForecastNotFoundError,
    ForecastRepository,
)

from backend.app.domain.feasibility import evaluate_campaign_feasibility
from backend.app.security.auth import get_current_user


router = APIRouter(tags=["Proposals & Approvals"], dependencies=[Depends(get_current_user)])


# ============================================================
# SPENDING AUTHORITY LIMITS
# ============================================================

ROLE_SPENDING_LIMITS = {
    "MGR-MKT": 7500.0,
    "MGR-STORE": 10000.0,
    "MGR-INV": 20000.0,
    "APPR-FIN": 50000.0,
    "DIR-MKT": 100000.0,
    "EXEC-DIR": 250000.0,
    "SYS-ADMIN": 1000000.0,
}


# ============================================================
# DATE NORMALIZATION
# ============================================================

def normalize_date(value):
    """Convert date, datetime or ISO date string into date."""

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).date()

    raise ValueError("Invalid date value.")


# ============================================================
# CREATE CAMPAIGN PROPOSAL
# ============================================================

@router.post(
    "/campaigns/proposals",
    response_model=ProposalResponse
)
def create_campaign_proposal(
    request: ProposalCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Generate and persist a campaign proposal backed by
    deterministic feasibility validation.
    """

    camp_repo = CampaignRepository(db)
    inv_repo = InventoryRepository(db)
    
    fc_repo = ForecastRepository()
    prop_repo = ProposalRepository(db)

    # 1. Retrieve campaign
    camp_data = camp_repo.get_campaign(request.campaign_id)

    if not camp_data:
        raise HTTPException(
            status_code=404,
            detail=f"Campaign '{request.campaign_id}' not found.",
        )

    # 2. Retrieve campaign cost assumptions
    try:
        cost_assumptions = camp_repo.get_cost_assumption(request.campaign_id)
    except LookupError as exc:
        raise HTTPException(status_code=422, detail="Cost assumptions are not configured for this campaign.") from exc

    # 3. Gather product information
    product_data = {}

    duration_days = (
        camp_data["end_date"] - camp_data["start_date"]
    ).days + 1

    for pid in camp_data["target_product_ids"]:

        # Product metadata must exist.
        p_meta = camp_repo.get_product(pid)

        if not p_meta:
            raise HTTPException(
                status_code=422,
                detail=f"Product metadata missing for '{pid}'.",
            )

        base_price = p_meta.get("base_price")

        try:
            base_price = float(base_price)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=422,
                detail=f"Invalid base price for product '{pid}'.",
            )

        if not math.isfinite(base_price) or base_price <= 0:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid base price for product '{pid}'.",
            )

        # Inventory evidence
        inv_snap = inv_repo.get_inventory_snapshot(pid)

        # Supplier evidence
        supp_info = inv_repo.get_supplier_replenishment(pid)

        # Forecast retrieval
        try:
            fc_res = fc_repo.get_forecast(
                product_id=pid,
                start_date=camp_data["start_date"],
                horizon_days=duration_days,
                model=FORECAST_MODEL,
            )

        except ForecastNotFoundError as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

        except ForecastDataError as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Forecast data is currently unavailable "
                    "or invalid."
                ),
            ) from exc

        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

        product_data[pid] = {
            "product_name": p_meta["product_name"],
            "base_price": base_price,
            "inventory": inv_snap,
            "supplier": supp_info,
            "baseline_forecast": fc_res.total_forecast_units,
        }

    # 4. Build feasibility request
    feas_req = FeasibilityRequest(
        campaign_id=request.campaign_id,
        product_ids=camp_data["target_product_ids"],
        start_date=camp_data["start_date"],
        end_date=camp_data["end_date"],
        budget_limit=camp_data["campaign_budget"],
        assumed_uplift_pct=0.20,
    )

    # 5. Evaluate deterministic feasibility
    feasibility_res = evaluate_campaign_feasibility(
        request=feas_req,
        campaign_budget=camp_data["campaign_budget"],
        discount_rate=camp_data["discount_rate"],
        cost_assumptions=cost_assumptions,
        product_data=product_data,
    )

    # 6. Determine initial proposal status
    proposal_id = (
        f"PROP-{datetime.now(timezone.utc).strftime('%Y%m%d')}-"
        f"{uuid.uuid4().hex[:6].upper()}"
    )

    is_feasible = (
        feasibility_res.status == "feasible_for_review"
    )

    decision_status = (
        "ranked_feasible"
        if is_feasible
        else "rejected_by_policy"
    )

    initial_approval_status = (
        "pending_review"
        if is_feasible
        else "rejected"
    )

    # 7. Persist proposal
    proposal = prop_repo.save_proposal(
        proposal_id=proposal_id,
        campaign_id=request.campaign_id,
        forecast_version=request.forecast_version,
        decision_status=decision_status,
        selected_option_id=request.selected_option_id,
        budget_validation_status=feasibility_res.budget_validation,
        inventory_validation_status=feasibility_res.inventory_validation,
        approval_status=initial_approval_status,
        approver_id="PENDING_ASSIGNMENT",
        created_by=current_user["sub"],
        created_by_role=current_user["role"],
    )

    return proposal


# ============================================================
# LIST PROPOSALS FOR SUBMITTER / REVIEWER QUEUE
# ============================================================

@router.get("/campaigns/proposals")
def list_campaign_proposals(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all proposals for reviewers, or only the caller's proposals for submitters."""
    repository = ProposalRepository(db)
    proposals = repository.list_proposals()
    if current_user.get("role") == "PROPOSAL-SUBMITTER":
        proposals = [
            item for item in proposals
            if item.get("created_by") == current_user.get("sub")
        ]
    return {"proposals": proposals}


# ============================================================
# GET CAMPAIGN PROPOSAL
# ============================================================

@router.get(
    "/campaigns/proposals/{proposal_id}",
    response_model=ProposalResponse,
)
def get_campaign_proposal(
    proposal_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve proposal status and validation outcomes.
    """

    prop_repo = ProposalRepository(db)

    proposal = prop_repo.get_proposal(proposal_id)

    if not proposal:
        raise HTTPException(
            status_code=404,
            detail=f"Proposal '{proposal_id}' not found.",
        )

    return proposal


@router.get("/campaigns/proposals/{proposal_id}/audit")
def get_proposal_audit_events(
    proposal_id: str,
    db: Session = Depends(get_db),
):
    """Return the append-only lifecycle events recorded for a proposal."""
    repository = ProposalRepository(db)
    proposal = repository.get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found.")
    return {
        "proposal_id": proposal_id,
        "events": repository.get_audit_events(proposal_id),
    }


# ============================================================
# APPROVE OR REJECT PROPOSAL
# ============================================================

@router.post(
    "/campaigns/proposals/{proposal_id}/approval",
    response_model=ApprovalResponse,
)
def approve_or_reject_proposal(
    proposal_id: str,
    request: ApprovalRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Process authorized human approval or rejection.

    Validates:
    - Approver role
    - Spending authority
    - Proposal state
    - Inventory availability
    - Safety stock
    - Supplier readiness
    - Replenishment constraints
    """

    prop_repo = ProposalRepository(db)
    camp_repo = CampaignRepository(db)
    inv_repo = InventoryRepository(db)

    # --------------------------------------------------------
    # 1. Retrieve proposal
    # --------------------------------------------------------

    proposal = prop_repo.get_proposal(proposal_id)

    if not proposal:
        raise HTTPException(
            status_code=404,
            detail=f"Proposal '{proposal_id}' not found.",
        )

    # --------------------------------------------------------
    # 2. Retrieve campaign
    # --------------------------------------------------------

    camp_data = camp_repo.get_campaign(proposal.campaign_id)

    if not camp_data:
        raise HTTPException(
            status_code=404,
            detail=f"Campaign '{proposal.campaign_id}' not found.",
        )

    # --------------------------------------------------------
    # 3. Validate approver role
    # --------------------------------------------------------

    authenticated_id = current_user["sub"]
    authenticated_role = current_user["role"]

    # Reject forged legacy fields instead of allowing a caller to claim
    # another employee's identity or spending authority.
    if request.approver_id and request.approver_id != authenticated_id:
        raise HTTPException(status_code=403, detail="Approver identity must match the authenticated user.")
    if request.approver_role and request.approver_role != authenticated_role:
        raise HTTPException(status_code=403, detail="Approver role is derived from the authenticated identity.")

    role_limit = ROLE_SPENDING_LIMITS.get(authenticated_role)
    if role_limit is None:
        raise HTTPException(
            status_code=403,
            detail=f"Unrecognized approver role '{authenticated_role}'.",
        )

    # --------------------------------------------------------
    # 4. Validate spending authority
    # --------------------------------------------------------

    campaign_budget = float(camp_data["campaign_budget"])

    if (
        request.action == "approve"
        and campaign_budget > role_limit
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                f"Spending limit exceeded: Role "
                f"'{authenticated_role}' authority limit "
                f"(${role_limit:,.2f}) is lower than campaign "
                f"budget (${campaign_budget:,.2f})."
            ),
        )

    if request.action == "approve":
        creation_event = next(
            (
                event for event in prop_repo.get_audit_events(proposal_id)
                if event.get("event_type") == "proposal_created"
            ),
            None,
        )
        if creation_event and creation_event.get("actor_id") == authenticated_id:
            raise HTTPException(status_code=403, detail="The proposal creator cannot approve their own proposal.")

    # --------------------------------------------------------
    # 5. Check terminal proposal state
    # --------------------------------------------------------

    if proposal.approval_status in {"approved", "rejected"}:

        # An opposite decision cannot overwrite a final decision.
        if (
            request.action == "approve"
            and proposal.approval_status == "rejected"
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Proposal '{proposal_id}' was already rejected "
                    "and cannot be approved."
                ),
            )

        if (
            request.action == "reject"
            and proposal.approval_status == "approved"
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Proposal '{proposal_id}' was already approved "
                    "and cannot be rejected."
                ),
            )

        return ApprovalResponse(
            proposal_id=proposal.proposal_id,
            campaign_id=proposal.campaign_id,
            approval_status=proposal.approval_status,
            approver_id=proposal.approver_id,
            approver_role=authenticated_role,
            approved_at=proposal.approved_at,
            revalidation_status="already_processed",
            message=(
                f"Proposal '{proposal_id}' was already "
                f"{proposal.approval_status}."
            ),
        )

    # --------------------------------------------------------
    # 6. Only pending proposals can be processed
    # --------------------------------------------------------

    if proposal.approval_status != "pending_review":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Proposal cannot be processed from status "
                f"'{proposal.approval_status}'."
            ),
        )

    # --------------------------------------------------------
    # 7. Perform approval revalidation
    # --------------------------------------------------------

    if request.action == "approve":

        campaign_start = normalize_date(
            camp_data["start_date"]
        )

        campaign_end = normalize_date(
            camp_data["end_date"]
        )

        for pid in camp_data["target_product_ids"]:

            # Inventory evidence
            inv = inv_repo.get_inventory_snapshot(pid)

            if not inv:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Pre-approval revalidation failed: "
                        f"Missing inventory snapshot for '{pid}'."
                    ),
                )

            available_stock = (
                inv["on_hand_stock"] - inv["reserved_stock"]
            )

            if available_stock < inv["safety_stock"]:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Pre-approval revalidation failed: "
                        f"Safety stock violation detected on '{pid}'."
                    ),
                )

            # Supplier evidence
            supplier = inv_repo.get_supplier_replenishment(pid)

            if not supplier:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Pre-approval revalidation failed: "
                        f"Missing supplier evidence for '{pid}'."
                    ),
                )

            supplier_status = (
                supplier.get("supplier_status") or ""
            ).strip().lower()

            if supplier_status != "active":
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Supplier for '{pid}' is not active."
                    ),
                )

            # Lead time validation
            lead_time_days = supplier.get("lead_time_days")

            if lead_time_days is None or lead_time_days <= 0:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Invalid or missing supplier lead time "
                        f"for '{pid}'."
                    ),
                )

            # MOQ validation
            minimum_order_quantity = supplier.get(
                "minimum_order_quantity"
            )

            if (
                minimum_order_quantity is None
                or minimum_order_quantity <= 0
            ):
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid MOQ for '{pid}'.",
                )

            # Replenishment capacity validation
            replenishment_capacity = supplier.get(
                "replenishment_capacity"
            )

            if (
                replenishment_capacity is None
                or replenishment_capacity < minimum_order_quantity
            ):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Invalid replenishment capacity "
                        f"for '{pid}'."
                    ),
                )

            # Expected replenishment date validation
            expected_date = supplier.get(
                "expected_replenishment_date"
            )

            if expected_date is None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Missing expected replenishment date "
                        f"for '{pid}'."
                    ),
                )

            expected_date = normalize_date(expected_date)

            if expected_date > campaign_end:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Replenishment for '{pid}' arrives after "
                        f"the campaign ends."
                    ),
                )

        new_status = "approved"
        revalidation_status = "passed"

        message = (
            f"Proposal '{proposal_id}' successfully approved "
            f"by {authenticated_id} "
            f"({authenticated_role})."
        )

    else:

        new_status = "rejected"
        revalidation_status = "not_applicable"

        message = (
            f"Proposal '{proposal_id}' rejected by "
            f"{authenticated_id} "
            f"({authenticated_role})."
        )

    # --------------------------------------------------------
    # 8. Persist approval decision
    # --------------------------------------------------------

    try:
        updated_prop = prop_repo.update_approval(
            proposal_id=proposal_id,
            approval_status=new_status,
            approver_id=authenticated_id,
            approver_role=authenticated_role,
            comments=request.comments,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if updated_prop is None:
        raise HTTPException(
            status_code=404,
            detail=f"Proposal '{proposal_id}' could not be updated.",
        )

    return ApprovalResponse(
        proposal_id=proposal_id,
        campaign_id=proposal.campaign_id,
        approval_status=new_status,
        approver_id=authenticated_id,
        approver_role=authenticated_role,
        approved_at=updated_prop.approved_at,
        revalidation_status=revalidation_status,
        message=message,
    )


# ============================================================
# ACTIVATE CAMPAIGN PROPOSAL
# ============================================================

@router.post(
    "/campaigns/proposals/{proposal_id}/activation",
    response_model=ActivationResponse,
)
def activate_campaign_proposal(
    proposal_id: str,
    request: ActivationRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Activate an approved campaign proposal.

    Governance rules:
    - Only approved proposals can be activated.
    - Rejected or pending proposals cannot be activated.
    - Duplicate activation requests are blocked.
    - Human approval is mandatory before activation.
    """

    authenticated_id = current_user["sub"]
    authenticated_role = current_user["role"]
    if authenticated_role not in {"SYS-ADMIN", "OPS-MANAGER", "MGR-STORE"}:
        raise HTTPException(status_code=403, detail="Insufficient permissions to activate campaigns.")
    if request.activator_id and request.activator_id != authenticated_id:
        raise HTTPException(status_code=403, detail="Activator identity must match the authenticated user.")

    prop_repo = ProposalRepository(db)

    # 1. Retrieve proposal
    proposal = prop_repo.get_proposal(proposal_id)

    if not proposal:
        raise HTTPException(
            status_code=404,
            detail=f"Proposal '{proposal_id}' not found.",
        )

    # Enforce four-eyes governance: approver and activator must differ.
    if proposal.approver_id == authenticated_id:
        raise HTTPException(status_code=403, detail="The approver cannot activate the same proposal.")

    # 2. Prevent duplicate activation
    if proposal.activated_at is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Duplicate activation request: Proposal "
                f"'{proposal_id}' has already been activated."
            ),
        )

    # 3. Only approved proposals can be activated
    if proposal.approval_status != "approved":
        raise HTTPException(
            status_code=403,
            detail=(
                f"Unauthorized activation rejected: Proposal "
                f"'{proposal_id}' cannot be activated because "
                f"its status is '{proposal.approval_status}' "
                "(must be approved by an authorized authority)."
            ),
        )

    # 4. Revalidate live inventory and supplier evidence immediately before
    # activation. Approval can become stale between approval and launch.
    camp_repo = CampaignRepository(db)
    inv_repo = InventoryRepository(db)
    campaign = camp_repo.get_campaign(proposal.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found during activation revalidation.")

    campaign_end = normalize_date(campaign["end_date"])
    for product_id in campaign["target_product_ids"]:
        inventory = inv_repo.get_inventory_snapshot(product_id)
        if not inventory:
            raise HTTPException(status_code=422, detail=f"Activation revalidation failed: missing inventory for '{product_id}'.")
        available = inventory["on_hand_stock"] - inventory["reserved_stock"]
        if available < inventory["safety_stock"]:
            raise HTTPException(status_code=422, detail=f"Activation revalidation failed: safety stock violation for '{product_id}'.")

        supplier = inv_repo.get_supplier_replenishment(product_id)
        if not supplier:
            raise HTTPException(status_code=422, detail=f"Activation revalidation failed: missing supplier evidence for '{product_id}'.")
        if (supplier.get("supplier_status") or "").strip().lower() != "active":
            raise HTTPException(status_code=422, detail=f"Activation revalidation failed: supplier for '{product_id}' is not active.")
        lead_time = supplier.get("lead_time_days")
        moq = supplier.get("minimum_order_quantity")
        capacity = supplier.get("replenishment_capacity")
        expected_date = supplier.get("expected_replenishment_date")
        if lead_time is None or lead_time <= 0:
            raise HTTPException(status_code=422, detail=f"Activation revalidation failed: invalid lead time for '{product_id}'.")
        if moq is None or moq <= 0 or capacity is None or capacity < moq:
            raise HTTPException(status_code=422, detail=f"Activation revalidation failed: invalid MOQ/capacity for '{product_id}'.")
        if expected_date is None or normalize_date(expected_date) > campaign_end:
            raise HTTPException(status_code=422, detail=f"Activation revalidation failed: replenishment timing invalid for '{product_id}'.")

    # 5. Persist activation atomically; repository guards against concurrent duplicates.
    try:
        activated_prop = prop_repo.update_activation(
            proposal_id=proposal_id,
            activator_id=authenticated_id,
            activator_role=authenticated_role,
            channel=request.channel,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if activated_prop is None:
        raise HTTPException(
            status_code=404,
            detail=f"Proposal '{proposal_id}' could not be activated.",
        )

    return ActivationResponse(
        proposal_id=proposal_id,
        campaign_id=proposal.campaign_id,
        status="activated",
        activated_at=activated_prop.activated_at,
        message=(
            f"Campaign '{proposal.campaign_id}' successfully "
            f"activated by {authenticated_id} "
            f"across {request.channel}."
        ),
    )
