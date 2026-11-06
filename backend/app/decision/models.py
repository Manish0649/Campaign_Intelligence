from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field

class ObjectiveWeights(BaseModel):
    """
    Documented business priorities and objective trade-off weights (must sum to 1.0).
    """
    expected_contribution: float = Field(0.35, ge=0.0, le=1.0, description="Weight for net margin (Revenue - Cost)")
    inventory_suitability: float = Field(0.25, ge=0.0, le=1.0, description="Weight for supply-to-demand coverage ratio")
    stockout_exposure_reduction: float = Field(0.20, ge=0.0, le=1.0, description="Weight for avoiding near-zero safety stock buffers")
    cost_efficiency: float = Field(0.10, ge=0.0, le=1.0, description="Weight for Contribution / Budget efficiency ratio")
    segment_priority: float = Field(0.10, ge=0.0, le=1.0, description="Weight for high-value customer segment focus")

class CandidateOption(BaseModel):
    """
    Structured campaign option with pre-calculated financial and supply attributes.
    """
    campaign_id: str
    campaign_name: str
    campaign_type: str
    target_product_ids: List[str]
    target_segments: str
    campaign_budget: float
    discount_rate: float
    total_projected_cost: float
    projected_units: float
    gross_revenue: float
    expected_contribution: float
    projected_supply: int
    net_usable_stock: int
    stock_coverage_ratio: float
    stockout_risk_score: float
    feasibility_status: str
    is_feasible: bool

class RankedCandidate(BaseModel):
    """
    A candidate ranked by a decision framework with score breakdown and rationale.
    """
    rank: int
    campaign_id: str
    campaign_name: str
    composite_score: float
    objective_scores: Dict[str, float]
    rationale: str

class DecisionInput(BaseModel):
    """
    Typed input contract for decision layer evaluation.
    """
    decision_question: str = (
        "Among the supplied feasible campaign options, which provides the best balance "
        "of expected contribution, campaign cost, inventory suitability and operational risk?"
    )
    candidates: List[CandidateOption]
    weights: ObjectiveWeights = Field(default_factory=ObjectiveWeights)
    forecast_version: str = "m5-dynamic-linear-v2"
    framework: Literal["laya"] = Field("laya", description="Laya decision framework")

class DecisionOutput(BaseModel):
    """
    Normalized application-level decision response schema.
    """
    proposal_id: Optional[str] = None
    forecast_version: str
    candidate_campaign_ids: List[str]
    feasible_candidate_ids: List[str]
    selected_campaign_id: Optional[str]
    ranked_candidates: List[RankedCandidate]
    objective_values: Dict[str, float]
    constraint_validation_status: str
    decision_rationale: str
    framework_used: str
    fallback_triggered: bool = False
    execution_latency_ms: float
    approval_status: str = "pending_review"
