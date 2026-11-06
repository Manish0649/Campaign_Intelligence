from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator

class CampaignBase(BaseModel):
    campaign_id: str = Field(..., description="Unique campaign identifier")
    campaign_name: str = Field(..., description="Human-readable campaign title")
    campaign_type: str = Field(..., description="e.g. flash_sale, weekly_special, clearance")
    start_date: date
    end_date: date
    target_product_ids: List[str] = Field(..., description="List of target product IDs (max 2 allowed)")
    target_segments: str = Field(..., description="Target customer segment")
    campaign_budget: float = Field(..., gt=0, description="Total budget limit in USD")
    discount_rate: float = Field(..., ge=0.0, le=1.0, description="Discount rate between 0 and 1")
    scenario_label: Optional[str] = Field("SCN-01: Baseline Scenario", description="Assumed scenario tag")

    @field_validator("target_product_ids")
    @classmethod
    def validate_product_limit(cls, v):
        if len(v) > 2:
            raise ValueError("Campaign scope violation: A campaign may target at most 2 product IDs simultaneously.")
        if len(v) == 0:
            raise ValueError("A campaign must target at least 1 product ID.")
        return v

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v, info):
        if "start_date" in info.data and v < info.data["start_date"]:
            raise ValueError("end_date must be greater than or equal to start_date.")
        return v

class CampaignCreate(CampaignBase):
    pass

class CampaignResponse(CampaignBase):
    model_config = ConfigDict(from_attributes=True)
    status: str = "candidate"

class CampaignCostAssumption(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    campaign_id: str
    fixed_campaign_cost: float = Field(default=800.0, ge=0.0)
    cost_per_contact: float = Field(default=0.08, ge=0.0)
    discount_cost_assumption: str = Field(default="retailer_absorbed")
    logistics_cost_assumption: float = Field(default=1.20, ge=0.0)
    cost_accounting_method: str = Field(default="activity_based_costing")


class CampaignBudgetStatus(BaseModel):
    campaign_id: str
    budget_limit: float
    total_projected_cost: float
    budget_remaining: float
    budget_validation_status: str
    cost_breakdown: dict

