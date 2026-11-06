from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

from backend.app.decision.models import (
    DecisionInput, DecisionOutput, CandidateOption, ObjectiveWeights
)
from backend.app.decision.laya_adapter import LayaAdapter
from backend.app.agents.graph import orchestrate_campaign_planning
from backend.app.security.auth import get_current_user

router = APIRouter(prefix="/decision", tags=["Decision Layer (Day 5)"], dependencies=[Depends(get_current_user)])

class OrchestratedProposalRequest(BaseModel):
    campaign_ids: Optional[List[str]] = Field(default=None, description="Subset of candidate campaigns (or None for top catalogue candidates)")
    decision_framework: Literal["laya"] = Field(default="laya", description="Laya decision framework")
    assumed_uplift_pct: float = Field(default=0.20, ge=0.0, le=2.0)

@router.post("/rank", response_model=DecisionOutput)
def rank_campaign_candidates(input_data: DecisionInput):
    """
    Ranks feasible candidate campaigns using the Laya decision framework
    with deterministic feasibility filtering and Laya scoring.
    """
    input_data.framework = "laya"
    return LayaAdapter().evaluate(input_data)

@router.post("/orchestrate", tags=["Agent Orchestration"])
def run_orchestrated_planning(req: OrchestratedProposalRequest):
    """
    Executes the end-to-end LangGraph Campaign Planning workflow:
    1. Candidate Preparation + Feasibility -> 2. Laya Decision Ranking -> 3. Proposal Persistence
    """
    result = orchestrate_campaign_planning(
        campaign_ids=req.campaign_ids,
        decision_framework=req.decision_framework,
        assumed_uplift_pct=req.assumed_uplift_pct
    )
    return {
        "status": "success" if not result.get("has_errors") else "failed",
        "current_step": result.get("current_step"),
        "selected_campaign": result.get("decision_result", {}).get("selected_campaign_id"),
        "generated_proposal": result.get("generated_proposal"),
        "decision_result": result.get("decision_result"),
        "feasible_options_count": len(result.get("feasible_options", [])),
        "infeasible_options_count": len(result.get("infeasible_options", [])),
        "audit_log": result.get("audit_log", [])
    }

