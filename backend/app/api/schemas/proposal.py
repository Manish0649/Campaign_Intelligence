from datetime import date, datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict

class FeasibilityRequest(BaseModel):
    campaign_id: str
    product_ids: List[str] = Field(..., max_length=2, min_length=1)
    start_date: date
    end_date: date
    budget_limit: Optional[float] = Field(None, gt=0, description="Override or client budget limit")
    assumed_uplift_pct: float = Field(default=0.20, ge=0.0, le=2.0, description="Hypothetical promotional demand increment")
    target_audience_size: Optional[int] = Field(default=5000, ge=100)

class ProductFeasibilityDetail(BaseModel):
    product_id: str
    product_name: str
    baseline_forecast_units: float
    promotional_demand_units: float
    on_hand_stock: int
    reserved_stock: int
    safety_stock: int
    net_usable_stock: int
    confirmed_replenishment_units: int
    projected_supply: int
    projected_surplus: float
    inventory_validation_status: str
    replenishment_validation_status: str
    warnings: List[str] = Field(default_factory=list)
    rejection_reasons: List[str] = Field(default_factory=list)

class FeasibilityResponse(BaseModel):
    campaign_id: str
    status: str = Field(..., description="'feasible_for_review' or 'rejected_by_policy'")
    forecast_version: str = "m5-dynamic-linear-v2"
    forecast_validation: str = Field(default="passed", description="'passed' or 'failed'")
    budget_validation: str = Field(..., description="'passed' or 'failed'")
    inventory_validation: str = Field(..., description="'passed' or 'failed'")
    replenishment_validation: str = Field(..., description="'passed' or 'failed'")
    total_projected_cost: float
    budget_limit: float
    warnings: List[str] = Field(default_factory=list)
    rejection_reasons: List[str] = Field(default_factory=list)
    approval_required: bool = True
    product_details: List[ProductFeasibilityDetail] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ProposalCreate(BaseModel):
    campaign_id: str
    forecast_version: str = "m5-dynamic-linear-v2"
    selected_option_id: str = "OPT-1-STANDARD"
    approver_id: Optional[str] = "PENDING_ASSIGNMENT"

class ProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    proposal_id: str
    campaign_id: str
    forecast_version: str
    decision_status: str
    selected_option_id: str
    budget_validation_status: str
    inventory_validation_status: str
    approval_status: str
    approver_id: str
    created_at: datetime
    approved_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None


class ApprovalRequest(BaseModel):
    # Legacy identity fields are accepted for client compatibility, but the
    # API never trusts them: identity and role are read from the signed JWT.
    approver_id: Optional[str] = None
    approver_role: Optional[str] = None
    action: Literal["approve", "reject"]
    comments: Optional[str] = Field(default=None, max_length=2000)

class ApprovalResponse(BaseModel):
    proposal_id: str
    campaign_id: str
    approval_status: str
    approver_id: str
    approver_role: str
    approved_at: Optional[datetime] = None
    revalidation_status: str
    message: str

class ActivationRequest(BaseModel):
    # Legacy activator_id is accepted but must match the authenticated subject.
    activator_id: Optional[str] = None
    channel: str = Field("marketing_ops", min_length=1, max_length=100)

class ActivationResponse(BaseModel):
    proposal_id: str
    campaign_id: str
    status: str
    activated_at: Optional[datetime] = None
    message: str

