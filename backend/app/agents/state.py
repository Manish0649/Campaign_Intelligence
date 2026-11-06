from typing import TypedDict, List, Dict, Any, Optional

class CampaignPlanningState(TypedDict):
    """
    Typed state representation for LangGraph Campaign Planning Orchestration.
    """
    campaign_ids: List[str]
    forecast_version: str
    decision_framework: str
    assumed_uplift_pct: float
    raw_candidates: List[Dict[str, Any]]
    policy_context: List[Dict[str, Any]]
    feasibility_evaluations: Dict[str, Any]
    feasible_options: List[Dict[str, Any]]
    infeasible_options: List[Dict[str, Any]]
    decision_result: Optional[Dict[str, Any]]
    generated_proposal: Optional[Dict[str, Any]]
    audit_log: List[str]
    current_step: str
    has_errors: bool
    error_message: Optional[str]

